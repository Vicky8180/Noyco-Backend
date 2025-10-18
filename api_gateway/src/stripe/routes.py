from fastapi import APIRouter, Depends, HTTPException, status, Request
# Import auth and schemas
from ...middlewares.jwt_auth import JWTAuthController
from .schemas import CheckoutBody, CheckoutURL, BillingCycle
from .webhooks.base import verify_stripe_signature
from .services import webhooks as dispatcher
from ..billing.schema import UserRole, PlanType, PlanStatus
from .client import get_stripe
from .audit import log
from .idempotency import generate as generate_idem
from .utils import build_subscription_metadata

from ...database.db import get_database
from .config import get_settings
from pydantic import BaseModel

stripe = get_stripe()
settings = get_settings()
db = get_database()

router = APIRouter(prefix="/stripe", tags=["Stripe"])
jwt_auth = JWTAuthController()

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _assert_subscription_ownership(sub, current_user):
    """Authorize that the stripe.Subscription belongs to the current user.

    Primary check: subscription.metadata.role_entity_id == user.role_entity_id
    Fallback: subscription.customer matches plan_doc.stripe_customer_id
    Raises HTTPException 403 if unauthorized.
    """
    if current_user.role != UserRole.INDIVIDUAL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only individual accounts supported")

    metadata = sub.get("metadata") or {}
    if metadata.get("role_entity_id") == current_user.role_entity_id:
        return

    # Fallback via stored plan customer id
    plan_doc = db.plans.find_one({"individual_id": current_user.role_entity_id}) or {}
    plan_customer = plan_doc.get("stripe_customer_id")
    if plan_customer and sub.get("customer") == plan_customer:
        return

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized")

def _ensure_subscription_metadata(sub, current_user):
    """If subscription lacks identifying metadata, patch it (best-effort)."""
    try:
        metadata = sub.get("metadata") or {}
        if metadata.get("role_entity_id") == current_user.role_entity_id:
            return sub
        # Only add if safe (avoid overwriting existing distinct owner)
        if not metadata.get("role_entity_id"):
            updated = stripe.Subscription.modify(
                sub.get("id"),
                metadata={
                    **metadata,
                    "role": current_user.role.value,
                    "role_entity_id": current_user.role_entity_id,
                }
            )
            return updated
    except Exception:
        pass
    return sub


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
# NOTE: Define static paths BEFORE dynamic catch-all like /subscription/{sub_id}
# to prevent 'current' from being interpreted as a subscription id.
# ---------------------------------------------------------------------------

@router.get("/subscription/current")
async def get_current_subscription(current_user=Depends(jwt_auth.get_current_user)):
    """Return a summary of the authenticated user's active subscription.

    For individuals we look up the plan document, then fetch the subscription
    from Stripe (best-effort). If anything is missing we return a minimal payload.
    """
    if current_user.role != UserRole.INDIVIDUAL:
        raise HTTPException(status_code=403, detail="Only individual accounts supported")
    plan_doc = db.plans.find_one({"individual_id": current_user.role_entity_id}) or {}
    subscription_id = plan_doc.get("stripe_subscription_id")
    schedule_id = plan_doc.get("stripe_schedule_id")
    summary = {
        "subscription_id": subscription_id,
        "schedule_id": schedule_id,
        "plan_type": plan_doc.get("plan_type"),
        "status": plan_doc.get("status"),
        "cancel_at_period_end": plan_doc.get("cancel_at_period_end"),
        "current_period_end": plan_doc.get("current_period_end"),
    }
    if not subscription_id and schedule_id:
        # Attempt to derive subscription id from schedule (e.g., webhook delay case)
        try:
            sched = stripe.SubscriptionSchedule.retrieve(schedule_id)
            derived_sub = sched.get("subscription")
            if derived_sub:
                summary["subscription_id"] = derived_sub
                subscription_id = derived_sub
        except Exception:
            pass
    if not subscription_id:
        return summary
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        summary.update({
            "stripe_status": sub.get("status"),
            "cancel_at_period_end": sub.get("cancel_at_period_end"),
            "current_period_end": sub.get("current_period_end"),
            "cancel_at": sub.get("cancel_at"),
            "plan_price": (sub.get("items", {}).get("data", [{}])[0].get("price", {}).get("id") if sub.get("items") else None),
        })
    except Exception:
        pass
    return summary

@router.get("/subscription/id/{sub_id}")
async def get_subscription_by_id(sub_id: str, current_user=Depends(jwt_auth.get_current_user)):
    """Explicit subscription retrieval by id to avoid path conflicts."""
    try:
        sub = stripe.Subscription.retrieve(sub_id)
        _assert_subscription_ownership(sub, current_user)
        # Attempt to heal metadata if missing
        sub = _ensure_subscription_metadata(sub, current_user)
        return sub
    except stripe.error.InvalidRequestError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/subscription/{sub_id}")
async def get_subscription(sub_id: str, current_user=Depends(jwt_auth.get_current_user)):
    """Legacy path (kept for backward compatibility). 'current' is reserved."""
    if sub_id == "current":
        raise HTTPException(status_code=400, detail="Use /stripe/subscription/current for the summary")
    try:
        sub = stripe.Subscription.retrieve(sub_id)
        _assert_subscription_ownership(sub, current_user)
        sub = _ensure_subscription_metadata(sub, current_user)
        return sub
    except stripe.error.InvalidRequestError as e:
        raise HTTPException(status_code=404, detail=str(e))


class CancelBody(BaseModel):
    subscription_id: str


@router.post("/subscription/cancel")
async def cancel_subscription(body: CancelBody, current_user=Depends(jwt_auth.get_current_user)):
    try:
        sub = stripe.Subscription.retrieve(body.subscription_id)
        _assert_subscription_ownership(sub, current_user)
        sub = _ensure_subscription_metadata(sub, current_user)

        # If already scheduled, return idempotent success
        if sub.get("cancel_at_period_end"):
            return {"status": sub.get("status"), "cancel_at_period_end": True, "current_period_end": sub.get("current_period_end")}

        canceled = None
        schedule_released = False
        try:
            # Preferred path: direct cancel at period end
            canceled = stripe.Subscription.modify(body.subscription_id, cancel_at_period_end=True)
        except stripe.error.InvalidRequestError as se:
            msg = (getattr(se, 'user_message', '') or str(se)).lower()
            if 'subscription schedule' in msg:
                # Release schedule to allow normal cancel_at_period_end semantics
                schedule_id = sub.get('schedule') or (db.plans.find_one({"individual_id": current_user.role_entity_id}) or {}).get('stripe_schedule_id')
                if not schedule_id:
                    raise HTTPException(status_code=400, detail="Schedule-managed subscription but schedule id not stored")
                try:
                    stripe.SubscriptionSchedule.release(schedule_id)
                    schedule_released = True
                    # Remove schedule id from plan doc so summary logic doesn't attempt fallback
                    try:
                        db.plans.update_one(
                            {"individual_id": current_user.role_entity_id},
                            {"$unset": {"stripe_schedule_id": ""}, "$set": {"released_schedule_id": schedule_id}}
                        )
                    except Exception:
                        pass
                    # Retry cancellation now that schedule is released
                    canceled = stripe.Subscription.modify(body.subscription_id, cancel_at_period_end=True)
                except stripe.error.InvalidRequestError as re_release:
                    raise HTTPException(status_code=400, detail=f"Unable to release schedule for cancellation: {re_release.user_message or str(re_release)}")
            else:
                raise
        # Persist cancellation schedule in our plans collection (individuals only for now)
        try:
            if current_user.role == UserRole.INDIVIDUAL:
                db.plans.update_one(
                    {"individual_id": current_user.role_entity_id},
                    {"$set": {
                        "cancel_at_period_end": True,
                        "current_period_end": (canceled.get("current_period_end") if isinstance(canceled, dict) else canceled.get("current_period_end")),
                        "stripe_subscription_status": (canceled.get("status") if isinstance(canceled, dict) else canceled.get("status")),
                        "updated_at": __import__("datetime").datetime.utcnow(),
                        "schedule_cancel_mode": False,  # now using direct subscription cancellation
                        "schedule_released_for_cancellation": schedule_released,
                    }}
                )
        except Exception:
            pass
        return {
            "status": (canceled.get('status') if isinstance(canceled, dict) else canceled.status),
            "cancel_at_period_end": (canceled.get("cancel_at_period_end") if isinstance(canceled, dict) else canceled.get("cancel_at_period_end")),
            "current_period_end": (canceled.get("current_period_end") if isinstance(canceled, dict) else canceled.get("current_period_end")),
            "managed_by_schedule": False,
            "schedule_released": schedule_released,
        }
    except stripe.error.InvalidRequestError as e:
        raise HTTPException(status_code=404, detail=str(e))


class ResumeBody(BaseModel):
    subscription_id: str


@router.post("/subscription/resume")
async def resume_subscription(body: ResumeBody, current_user=Depends(jwt_auth.get_current_user)):
    """Unset cancel_at_period_end so the subscription continues."""
    try:
        sub = stripe.Subscription.retrieve(body.subscription_id)
        _assert_subscription_ownership(sub, current_user)
        sub = _ensure_subscription_metadata(sub, current_user)
        if not sub.get("cancel_at_period_end"):
            # Idempotent: already active
            return {"status": sub.get("status"), "cancel_at_period_end": False, "current_period_end": sub.get("current_period_end")}
        resumed = None
        schedule_relinked = False
        try:
            resumed = stripe.Subscription.modify(body.subscription_id, cancel_at_period_end=False)
        except stripe.error.InvalidRequestError as se:
            msg = (getattr(se, 'user_message', '') or str(se)).lower()
            if 'subscription schedule' in msg:
                # If cancellation previously released the schedule we cannot relink automatically.
                # Just report active state.
                sub = stripe.Subscription.retrieve(body.subscription_id)
                resumed = sub
            else:
                raise
        try:
            if current_user.role == UserRole.INDIVIDUAL:
                db.plans.update_one(
                    {"individual_id": current_user.role_entity_id},
                    {"$set": {
                        "cancel_at_period_end": False,
                        "current_period_end": resumed.get("current_period_end"),
                        "stripe_subscription_status": resumed.get("status"),
                        "updated_at": __import__("datetime").datetime.utcnow(),
                        "schedule_relinked": schedule_relinked,
                    }}
                )
        except Exception:
            pass
        return {
            "status": resumed.get("status"),
            "cancel_at_period_end": resumed.get("cancel_at_period_end"),
            "current_period_end": resumed.get("current_period_end"),
            "schedule_relinked": schedule_relinked,
        }
    except stripe.error.InvalidRequestError as e:
        raise HTTPException(status_code=404, detail=str(e))

# ---------------------------------------------------------------------------
# Dev-only test route for sending sample billing emails (multipart)
# ---------------------------------------------------------------------------

@router.get("/email/test", include_in_schema=False)
async def email_test(type: str, to: str):
    env = getattr(settings, "ENVIRONMENT", "development").lower()
    if env == "production":
        raise HTTPException(status_code=403, detail="Not available in production")
    # Import here to avoid circulars
    from .services.notifications import _send_notification
    from .services.templates import render_templates
    from ...config import get_settings as _get
    s = _get()
    # Minimal vars to render
    vars = {
        "customerName": "Test User",
        "invoiceDate": "2025-10-15",
        "amount": "50.00",
        "currency": "USD",
        "plan": "Pro",
        "periodStart": "2025-10-01",
        "periodEnd": "2025-11-01",
        "dueDate": "2025-10-20",
        "manageBillingUrl": getattr(s, "MANAGE_BILLING_URL", "https://app.noyco.com/billing"),
        "supportEmail": getattr(s, "SUPPORT_EMAIL", "support@noyco.com"),
    }
    subjects = {
        "invoice_paid": "Payment received — thank you!",
        "invoice_failed": "We couldn't process your payment",
        "invoice_upcoming": "Upcoming invoice",
        "subscription_started": "Your subscription has started",
        "subscription_updated": "Your subscription has been updated",
        "subscription_canceled": "Your subscription has been canceled",
    }
    if type not in subjects:
        raise HTTPException(status_code=400, detail="Unknown type")
    rendered = render_templates(type, vars)
    from ...auth.email_service import _send_email
    _send_email(to, subjects[type], rendered["text"], html_body=rendered.get("html"))
    return {"status": "sent", "type": type, "to": to}

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

# ---------------------------------------------------------------------------
# Custom Checkout (Payment Element) - Authenticated subscription creation
# ---------------------------------------------------------------------------

class CreateSubscriptionBody(BaseModel):
    plan_type: PlanType


class CreateSubscriptionResponse(BaseModel):
    client_secret: str
    subscription_id: str
    customer_id: str


@router.post("/create-subscription", response_model=CreateSubscriptionResponse)
async def create_subscription(body: CreateSubscriptionBody, current_user=Depends(jwt_auth.get_current_user)):
    """Create a Stripe Subscription in default_incomplete state and return a client secret.

    This powers the custom checkout (Payment Element) flow for authenticated users.
    """
    # Only individuals supported in current release
    if current_user.role != UserRole.INDIVIDUAL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only individual accounts can purchase subscriptions")

    allowed_plans = {PlanType.ONE_MONTH, PlanType.THREE_MONTHS, PlanType.SIX_MONTHS}
    if body.plan_type not in allowed_plans:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plan type not supported. Choose one of: one_month, three_months, six_months",
        )

    now = __import__("datetime").datetime.utcnow()
    prev_status = None
    prev_plan_type = None

    # Map plan to intro price id (single source: StripeSettings)
    intro_price_map = {
        (UserRole.INDIVIDUAL.value, "one_month"): settings.IND_1M_INTRO_MONTHLY,
        (UserRole.INDIVIDUAL.value, "three_months"): settings.IND_3M_INTRO_QUARTERLY,
        (UserRole.INDIVIDUAL.value, "six_months"): settings.IND_6M_INTRO_SEMIANNUAL,
    }
    key = (current_user.role.value, body.plan_type.value)
    price_id = intro_price_map.get(key)
    if not price_id:
        raise HTTPException(status_code=400, detail="Intro price mapping not found for selected plan")

    try:
        # Upsert individual's plan as PENDING before creating subscription
        plan_doc = db.plans.find_one({"individual_id": current_user.role_entity_id})
        prev_status = plan_doc.get("status") if plan_doc else None
        prev_plan_type = plan_doc.get("plan_type") if plan_doc else None
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

        # Ensure a Stripe Customer exists (reuse if present)
        customer_id = None
        plan_doc = db.plans.find_one({"individual_id": current_user.role_entity_id}) or {}
        if plan_doc:
            customer_id = plan_doc.get("stripe_customer_id")
        if not customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={
                    "role": current_user.role.value,
                    "role_entity_id": current_user.role_entity_id,
                },
            )
            customer_id = customer.get("id")
            try:
                db.plans.update_one(
                    {"individual_id": current_user.role_entity_id},
                    {"$set": {"stripe_customer_id": customer_id, "updated_at": now}},
                )
            except Exception:
                pass

        # Idempotency for subscription creation
        import time, uuid as _uuid
        idem = generate_idem("sub_create", getattr(current_user, "user_id", "unknown"), body.plan_type.value, str(int(time.time())), _uuid.uuid4().hex)

        # Create subscription in default_incomplete state and expand PaymentIntent to get client_secret
        # Important: Disable automatic tax at creation to avoid 'customer_tax_location_invalid' when customer has no address.
        auto_tax_enabled = False
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price_id, "quantity": 1}],
            payment_behavior="default_incomplete",
            expand=["latest_invoice.payment_intent"],
            metadata=build_subscription_metadata(
                role=current_user.role.value,
                role_entity_id=current_user.role_entity_id,
                plan_type=body.plan_type.value,
                source=None,
            ),
            idempotency_key=idem,
        )

        latest_invoice = subscription.get("latest_invoice") or {}
        payment_intent = latest_invoice.get("payment_intent") or {}
        client_secret = payment_intent.get("client_secret")
        if not client_secret:
            raise HTTPException(status_code=502, detail="Missing client secret; unable to proceed with payment")

        # Diagnostics
        try:
            db.plans.update_one(
                {"individual_id": current_user.role_entity_id},
                {"$set": {
                    "last_subscription_attempt_at": now,
                    "last_subscription_id": subscription.get("id"),
                    "stripe_customer_id": customer_id,
                }}
            )
        except Exception:
            pass

        try:
            log("subscription_create", {
                "role": current_user.role.value,
                "role_entity_id": current_user.role_entity_id,
                "plan_type": body.plan_type.value,
                "customer_id": customer_id,
                "subscription_id": subscription.get("id"),
            }, "ok")
        except Exception:
            pass

        return CreateSubscriptionResponse(
            client_secret=client_secret,
            subscription_id=subscription.get("id"),
            customer_id=customer_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        # Revert plan state best-effort
        try:
            revert_status = prev_status if prev_status else PlanStatus.INACTIVE.value
            db.plans.update_one(
                {"individual_id": current_user.role_entity_id},
                {"$set": {
                    "status": revert_status,
                    "plan_type": prev_plan_type if prev_plan_type else body.plan_type.value,
                    "last_subscription_error": str(e)[:500],
                    "last_subscription_error_at": now,
                    "updated_at": now,
                }, "$inc": {"last_subscription_failed_attempts": 1}},
            )
        except Exception:
            pass

        try:
            log("subscription_create_failed", {
                "role": current_user.role.value,
                "role_entity_id": current_user.role_entity_id,
                "plan_type": body.plan_type.value,
            }, "error", str(e))
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="Unable to start subscription at the moment. Please try again in a minute.")
