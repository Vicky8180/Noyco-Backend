from fastapi import APIRouter, Depends, HTTPException, status, Request
# Import auth and schemas
from ...middlewares.jwt_auth import JWTAuthController
from .schemas import CheckoutBody, CheckoutURL, BillingCycle
from .services.sessions import create_checkout_session
from .webhooks.base import verify_stripe_signature
from .services import webhooks as dispatcher
from ..billing.schema import UserRole, PlanType, PlanStatus
from .client import get_stripe
from .audit import log

from ...database.db import get_database
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
    # Enforce individuals-only for current release
    if current_user.role != UserRole.INDIVIDUAL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only individual accounts can purchase subscriptions")

    # Validate only new Leapply plan types
    allowed_plans = {PlanType.ONE_MONTH, PlanType.THREE_MONTHS, PlanType.SIX_MONTHS}
    if body.plan_type not in allowed_plans:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plan type not supported. Choose one of: one_month, three_months, six_months",
        )

    # Prepare shared values for diagnostics and potential revert on failure
    now = __import__("datetime").datetime.utcnow()
    prev_status = None
    prev_plan_type = None
    try:
        # Upsert individual's plan as PENDING before creating checkout session
        # Try to find existing plan doc and remember previous state to revert if needed
        plan_doc = db.plans.find_one({"individual_id": current_user.role_entity_id})
        prev_status = plan_doc.get("status") if plan_doc else None
        prev_plan_type = plan_doc.get("plan_type") if plan_doc else None
        created_new = False
        if plan_doc:
            db.plans.update_one(
                {"_id": plan_doc.get("_id")},
                {"$set": {
                    "plan_type": body.plan_type.value,
                    "status": PlanStatus.PENDING.value,
                    "updated_at": now,
                }}
            )
        else:
            # Minimal plan doc with defaults; controller will enrich on activation
            created_new = True
            db.plans.insert_one({
                "id": __import__("uuid").uuid4().hex,
                "individual_id": current_user.role_entity_id,
                "plan_type": body.plan_type.value,
                "status": PlanStatus.PENDING.value,
                "selected_services": [],
                "memory_stack": [],
                "created_at": now,
                "updated_at": now,
            })

        # Create checkout session
        session = create_checkout_session(user=current_user, plan_type=body.plan_type.value)
        url = session["url"]
        session_id = session.get("id")

        # Persist last checkout session id for diagnostics
        try:
            # Best-effort: store last intent and session id to correlate
            update = {"last_checkout_intent_at": now}
            if session_id:
                update["last_checkout_session_id"] = session_id
            db.plans.update_one({"individual_id": current_user.role_entity_id}, {"$set": update})
        except Exception:
            pass

        return {"checkout_url": url}
    except ValueError:
        # Sessions service isn't yet wired for new plan types (handled in Task 5)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Checkout for this plan isn't configured yet. Please try again later.",
        )
    except Exception as e:
        # Broader failure (network/Stripe/transient). Revert/annotate pending state to avoid lingering PENDING.
        try:
            revert_status = prev_status if prev_status else PlanStatus.INACTIVE.value
            db.plans.update_one(
                {"individual_id": current_user.role_entity_id},
                {
                    "$set": {
                        "status": revert_status,
                        "plan_type": prev_plan_type if prev_plan_type else body.plan_type.value,
                        "last_checkout_error": str(e)[:500],
                        "last_checkout_error_at": now,
                        "updated_at": now,
                    },
                    "$inc": {"last_checkout_failed_attempts": 1},
                },
            )
        except Exception:
            pass
        # Audit the failure event (no sensitive data)
        try:
            log(
                "checkout_create_failed",
                {
                    "role": current_user.role.value,
                    "role_entity_id": current_user.role_entity_id,
                    "plan_type": body.plan_type.value,
                },
                "error",
                str(e),
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to start checkout at the moment. Please try again in a minute.",
        )

@router.post('/webhook', include_in_schema=False)
async def stripe_webhook(request: Request):
    """Fast-ACK webhooks to avoid Stripe CLI timeouts; process asynchronously."""
    event = await verify_stripe_signature(request)

    # Fire-and-forget task to process in the background
    import asyncio
    async def _process():
        try:
            await dispatcher.dispatch(event)
        except Exception as e:
            try:
                log("webhook_process_async", {"type": event.get("type"), "event_id": event.get("id")}, "error", str(e))
            except Exception:
                pass

    try:
        # Schedule without awaiting to immediately ACK
        asyncio.create_task(_process())
    except RuntimeError:
        # Fallback if no running loop (unlikely in FastAPI): process synchronously but bounded
        try:
            await asyncio.wait_for(dispatcher.dispatch(event), timeout=2.0)
        except Exception:
            pass

    return { 'status': 'accepted' }

# ---------------------------------------------------------------------------
# Customer Portal
# ---------------------------------------------------------------------------

@router.post("/portal-link")
async def create_billing_portal_link(current_user=Depends(jwt_auth.get_current_user)):
    """Return a Stripe Customer-Portal session URL so the user can manage billing."""

    # Guard: individuals only in this release
    if current_user.role != UserRole.INDIVIDUAL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only individual accounts have billing portal access in this release")

    # Determine where the plan is stored
    role = current_user.role
    customer_id = None

    plan_doc = db.plans.find_one({"individual_id": current_user.role_entity_id})
    if plan_doc:
        customer_id = plan_doc.get("stripe_customer_id")

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
        if role == UserRole.INDIVIDUAL and plan_doc:
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
