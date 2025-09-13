from fastapi import APIRouter, Depends, HTTPException, status, Request
# Import auth and schemas
from ...middlewares.jwt_auth import JWTAuthController
from .schemas import CheckoutBody, CheckoutURL
from .services.sessions import create_checkout_session
from .webhooks.base import verify_stripe_signature
from .services import webhooks as dispatcher
from ..billing.schema import UserRole
from .client import get_stripe

from api_gateway.database.db import get_database
from .config import get_settings
from pydantic import BaseModel

stripe = get_stripe()
settings = get_settings()
db = get_database()

router = APIRouter(prefix="/stripe", tags=["Stripe"])
jwt_auth = JWTAuthController()

# Checkout endpoint
@router.post("/checkout", response_model=CheckoutURL)
async def create_checkout(body: CheckoutBody, request: Request, current_user=Depends(jwt_auth.get_current_user)):
    # Simple role validation: both hospitals and individuals may choose lite or pro.
    allowed = ["lite", "pro"]
    if body.plan_type.value not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan type not supported")

    url = create_checkout_session(user=current_user, plan_type=body.plan_type.value, billing_cycle=body.billing_cycle)
    return {"checkout_url": url}

@router.post('/webhook', include_in_schema=False)
async def stripe_webhook(request: Request):
    event = await verify_stripe_signature(request)
    await dispatcher.dispatch(event)
    return {'status': 'success'}

# ---------------------------------------------------------------------------
# Customer Portal
# ---------------------------------------------------------------------------

@router.post("/portal-link")
async def create_billing_portal_link(current_user=Depends(jwt_auth.get_current_user)):
    """Return a Stripe Customer-Portal session URL so the user can manage billing."""

    # Determine where the plan is stored
    role = current_user.role
    customer_id = None

    if role == UserRole.HOSPITAL:
        plan_doc = db.plans.find_one({"hospital_id": current_user.role_entity_id})
        if plan_doc:
            customer_id = plan_doc.get("stripe_customer_id")
    elif role == UserRole.INDIVIDUAL:
        plan_doc = db.plans.find_one({"individual_id": current_user.role_entity_id})
        if plan_doc:
            customer_id = plan_doc.get("stripe_customer_id")
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only hospitals and individuals have billing portal access")

    # Lazily create a Customer if we don't have one yet
    if not customer_id:
        customer = stripe.Customer.create(
            email=current_user.email,
            metadata={
                "role": role.value,
                "role_entity_id": current_user.role_entity_id,
            },
        )
        customer_id = customer.id

        # Persist it
        if role == UserRole.HOSPITAL and plan_doc:
            db.plans.update_one({"_id": plan_doc.get("_id")}, {"$set": {"stripe_customer_id": customer_id}})
        elif role == UserRole.INDIVIDUAL and plan_doc:
            db.plans.update_one({"_id": plan_doc.get("_id")}, {"$set": {"stripe_customer_id": customer_id}})

    # Create portal session
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=settings.SUCCESS_URL,
    )

    return {"portal_url": session.url}

# ---------------------------------------------------------------------------
# Subscription management APIs (authenticated user)
# ---------------------------------------------------------------------------

@router.get("/subscription/{sub_id}")
async def get_subscription(sub_id: str, current_user=Depends(jwt_auth.get_current_user)):
    try:
        sub = stripe.Subscription.retrieve(sub_id)
        # Basic access control: user must own the subscription
        metadata = sub.get("metadata", {})
        if metadata.get("role_entity_id") != current_user.role_entity_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized")
        return sub
    except stripe.error.InvalidRequestError as e:
        raise HTTPException(status_code=404, detail=str(e))


class CancelBody(BaseModel):
    subscription_id: str


@router.post("/subscription/cancel")
async def cancel_subscription(body: CancelBody, current_user=Depends(jwt_auth.get_current_user)):
    try:
        sub = stripe.Subscription.retrieve(body.subscription_id)
        metadata = sub.get("metadata", {})
        if metadata.get("role_entity_id") != current_user.role_entity_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized")

        canceled = stripe.Subscription.modify(body.subscription_id, cancel_at_period_end=True)
        return {"status": canceled.status}
    except stripe.error.InvalidRequestError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/customer/{customer_id}/invoices")
async def list_invoices(customer_id: str, current_user=Depends(jwt_auth.get_current_user)):
    try:
        invoices = stripe.Invoice.list(customer=customer_id, limit=20)
        return invoices
    except stripe.error.InvalidRequestError as e:
        raise HTTPException(status_code=404, detail=str(e))

# ---------------------------------------------------------------------------
# Admin endpoints (require ADMIN role)
# ---------------------------------------------------------------------------

admin_router = APIRouter(prefix="/admin", tags=["Admin Billing"])


def admin_only(user=Depends(jwt_auth.get_current_user)):
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@admin_router.get("/customers")
async def list_customers(_: UserRole = Depends(admin_only)):
    return stripe.Customer.list(limit=100)


@admin_router.get("/subscriptions")
async def list_subscriptions(_: UserRole = Depends(admin_only)):
    return stripe.Subscription.list(limit=100)

# register admin_router
router.include_router(admin_router) 
