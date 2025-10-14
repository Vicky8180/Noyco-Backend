from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, EmailStr, Field
from typing import List, Literal, Optional, Dict
from time import time
import logging

# Stripe config and client
from ..stripe.config import get_settings as get_stripe_settings
from ..stripe.client import get_stripe
from ..stripe.idempotency import generate as generate_idem
from ..stripe.utils import build_subscription_metadata
from ...database.db import get_database
from ..billing.schema import UserRole
from ...config import get_settings as get_app_settings
from ..auth.email_service import send_signup_otp
from ..auth.controller import AuthController
from ..stripe.services.webhooks import handle_checkout_completed
from fastapi import Depends
from ...database.db import get_database

router = APIRouter(prefix="/public", tags=["Public Billing"])
logger = logging.getLogger("public.billing")


# -----------------------------
# Models
# -----------------------------

class PlanCatalogItem(BaseModel):
    code: Literal["IND_1M", "IND_3M", "IND_6M"]
    label: str
    months: int
    priceDisplay: Optional[str] = None  # kept for backward-compat; now equals introDisplay
    stripePriceId: str  # intro price id
    introDisplay: Optional[str] = None
    recurringDisplay: Optional[str] = None


class PlanCatalogResponse(BaseModel):
    plans: List[PlanCatalogItem]


class CheckoutSessionRequest(BaseModel):
    pass  # deprecated


class SessionStatusResponse(BaseModel):
    processed: bool
    email: Optional[str] = None
    userStatus: Optional[Literal["pending_verification", "active"]] = None
    planAssigned: Optional[bool] = None


class ResendOTPRequest(BaseModel):
    email: EmailStr


# -----------------------------
# Helpers: simple TTL cache + price formatting
# -----------------------------
_PLANS_CACHE: Dict[str, object] = {"value": None, "ts": 0.0}
_PLANS_TTL_SECONDS = 300


def _format_currency(amount: Optional[int], currency: Optional[str]) -> Optional[str]:
    if amount is None or currency is None:
        return None
    # Stripe prices are in the smallest unit (e.g., cents)
    try:
        major = amount / 100.0
        c = currency.upper()
        symbol = "$" if c == "USD" else ("₹" if c == "INR" else f"{c} ")
        return f"{symbol}{major:.2f}"
    except Exception:
        return None


def _fetch_catalog_from_stripe():
    """Build catalog from canonical price IDs in StripeSettings and enrich with live price amounts.

    Falls back to returning items without priceDisplay if Stripe retrieval fails.
    """
    settings = get_stripe_settings()
    stripe = get_stripe()

    mapping = [
        ("IND_1M", "1 Month", 1, settings.IND_1M_INTRO_MONTHLY, settings.IND_1M_RECUR_MONTHLY),
        ("IND_3M", "3 Months", 3, settings.IND_3M_INTRO_QUARTERLY, settings.IND_3M_RECUR_MONTHLY),
        ("IND_6M", "6 Months", 6, settings.IND_6M_INTRO_SEMIANNUAL, settings.IND_6M_RECUR_MONTHLY),
    ]

    plans: List[PlanCatalogItem] = []
    for code, label, months, intro_price_id, recur_price_id in mapping:
        intro_text = None
        recur_text = None
        try:
            # Build intro display: "$X.XX first N months" (or "first month")
            if intro_price_id:
                price_obj = stripe.Price.retrieve(intro_price_id)
                intro_amount = _format_currency(price_obj.get("unit_amount"), price_obj.get("currency"))
                if intro_amount:
                    if months == 1:
                        intro_text = f"{intro_amount} first month"
                    else:
                        intro_text = f"{intro_amount} total for first {months} months"
            # Build recurring display using recurring price id
            if recur_price_id:
                r_obj = stripe.Price.retrieve(recur_price_id)
                r_amount = _format_currency(r_obj.get("unit_amount"), r_obj.get("currency"))
                if r_amount:
                    recur_text = f"then {r_amount} every 1 month"
        except Exception:
            # Non-fatal: keep priceDisplay None
            pass
        # Backward-compat: priceDisplay mirrors introDisplay if available
        plans.append(PlanCatalogItem(
            code=code,
            label=label,
            months=months,
            priceDisplay=intro_text,
            stripePriceId=intro_price_id or "",
            introDisplay=intro_text,
            recurringDisplay=recur_text,
        ))

    return PlanCatalogResponse(plans=plans)


# -----------------------------
# Endpoints
# -----------------------------

@router.get("/billing/plans", response_model=PlanCatalogResponse)
async def get_public_plans():
    """Return the public individual plans catalog (no auth, no user state)."""
    app_settings = get_app_settings()
    if not getattr(app_settings, "FUNNEL_PUBLIC_BILLING_ENABLED", True):
        raise HTTPException(status_code=404, detail="Not found")
    now = time()
    if _PLANS_CACHE["value"] and (now - float(_PLANS_CACHE["ts"])) < _PLANS_TTL_SECONDS:
        return _PLANS_CACHE["value"]

    catalog = _fetch_catalog_from_stripe()
    _PLANS_CACHE["value"] = catalog
    _PLANS_CACHE["ts"] = now
    return catalog


@router.post("/billing/checkout-session")
async def create_public_checkout_session(body: CheckoutSessionRequest):
    raise HTTPException(status_code=410, detail="Legacy Checkout is no longer supported. Use /public/billing/create-subscription.")


@router.get("/stripe/session-status", response_model=SessionStatusResponse)
async def get_public_session_status(session_id: str = Query(..., alias="session_id")):
    """Return payment processing status for a given Checkout Session.

    processed = True when Stripe marks the session as paid; userStatus/planAssigned are
    optional and will be populated once fulfillment is implemented in webhook logic.
    """
    app_settings = get_app_settings()
    if not getattr(app_settings, "FUNNEL_PUBLIC_BILLING_ENABLED", True):
        raise HTTPException(status_code=404, detail="Not found")
    stripe = get_stripe()
    db = get_database()
    email = None
    processed = False
    user_status = None
    plan_assigned = None

    # First, consult DB marker set by webhook
    marker = db.webhook_checkouts.find_one({"session_id": session_id}) or {}
    if marker:
        processed = bool(marker.get("processed"))
        email = marker.get("email")

    # Optionally confirm with Stripe session (source of truth for payment success)
    if not processed:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            payment_status = session.get("payment_status")
            status_str = session.get("status")
            if payment_status == "paid" and status_str in ("complete", "expired"):
                processed = True
                # capture email if missing
                details = session.get("customer_details") or {}
                email = email or details.get("email") or session.get("customer_email")
                # Dev-only safety net: if webhook didn't run yet, backfill fulfillment now
                try:
                    env = getattr(get_app_settings(), "ENVIRONMENT", "development").lower()
                except Exception:
                    env = "development"
                if env != "production" and not marker:
                    try:
                        # Synthesize a minimal checkout.session.completed event and invoke the handler
                        fake_event = {
                            "id": f"evt_manual_{session_id}",
                            "type": "checkout.session.completed",
                            "data": {"object": session},
                        }
                        await handle_checkout_completed(fake_event)
                        # Refresh marker after fulfillment
                        marker = db.webhook_checkouts.find_one({"session_id": session_id}) or {}
                        processed = bool(marker.get("processed", True))
                    except Exception:
                        # Non-fatal: if backfill fails, leave processed=True based on Stripe
                        pass
        except Exception:
            pass

    # If processed, try to infer userStatus and planAssigned using email
    if processed and email:
        user = db.users.find_one({"email": email}) or {}
        role_entity_id = user.get("role_entity_id")
        email_verified = bool(user.get("email_verified", False))
        user_status = "active" if email_verified else "pending_verification"
        if user.get("role") == UserRole.INDIVIDUAL.value and role_entity_id:
            plan_doc = db.plans.find_one({"individual_id": role_entity_id}) or {}
            plan_assigned = bool(plan_doc.get("status") in ("active", "pending", "past_due"))

    logger.info("session_status", extra={"session_id": session_id, "processed": processed, "email": email, "user_status": user_status, "plan_assigned": bool(plan_assigned)})
    return SessionStatusResponse(processed=processed, email=email, userStatus=user_status, planAssigned=plan_assigned)


# -----------------------------------------------------------------------------
# Custom Checkout (Payment Element) - Public create-subscription
# -----------------------------------------------------------------------------

class PublicCreateSubscriptionRequest(BaseModel):
    email: EmailStr
    plan_code: Literal["IND_1M", "IND_3M", "IND_6M"]


class PublicCreateSubscriptionResponse(BaseModel):
    client_secret: str
    subscription_id: str
    customer_id: str


@router.post("/billing/create-subscription", response_model=PublicCreateSubscriptionResponse)
async def public_create_subscription(body: PublicCreateSubscriptionRequest):
    """Create a Subscription for public funnel (no auth) and return a client secret."""
    app_settings = get_app_settings()
    if not getattr(app_settings, "FUNNEL_PUBLIC_BILLING_ENABLED", True):
        raise HTTPException(status_code=404, detail="Not found")

    settings = get_stripe_settings()
    stripe = get_stripe()

    code_to_price_and_plan = {
        "IND_1M": (settings.IND_1M_INTRO_MONTHLY, "one_month"),
        # For 3M and 6M, use per-period intro prices to bill upfront once
        "IND_3M": (settings.IND_3M_INTRO_QUARTERLY, "three_months"),
        "IND_6M": (settings.IND_6M_INTRO_SEMIANNUAL, "six_months"),
    }
    price_id, plan_type = code_to_price_and_plan.get(body.plan_code, (None, None))
    if not price_id or not plan_type:
        raise HTTPException(status_code=400, detail="Unsupported or unconfigured plan_code")

    # Ensure/retrieve customer by email
    customer_id = None
    try:
        # Search by email (Stripe API: list is limited; for test env this is acceptable)
        existing = stripe.Customer.list(email=body.email, limit=1)
        if existing and existing.get("data"):
            customer_id = existing["data"][0]["id"]
    except Exception:
        customer_id = None
    if not customer_id:
        cust = stripe.Customer.create(email=body.email, metadata={"role": UserRole.INDIVIDUAL.value})
        customer_id = cust.get("id")

    # Idempotency: scope by email+plan+ts
    import uuid
    idem = generate_idem("public_sub_create", body.email, body.plan_code, str(int(time())), uuid.uuid4().hex)

    # Determine if the customer has a resolvable tax location. If not, disable automatic tax to prevent
    # "customer_tax_location_invalid" errors when creating subscriptions without addresses.
    auto_tax_enabled = True
    try:
        cust_obj = stripe.Customer.retrieve(customer_id)
        addr = (cust_obj.get("address") or {})
        ship_addr = ((cust_obj.get("shipping") or {}).get("address") if cust_obj.get("shipping") else None)
        has_location = bool((addr and addr.get("country")) or (ship_addr and ship_addr.get("country")))
        if not has_location:
            auto_tax_enabled = False
            logger.info("auto_tax_disabled_no_customer_location", extra={"customer_id": customer_id, "email": body.email})
    except Exception:
        # If we cannot determine, be safe and disable to avoid hard failures in the funnel
        auto_tax_enabled = False
        logger.info("auto_tax_disabled_lookup_failed", extra={"customer_id": customer_id, "email": body.email})

    try:
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price_id, "quantity": 1}],
            payment_behavior="default_incomplete",
            expand=["latest_invoice.payment_intent"],
            metadata=build_subscription_metadata(
                role=UserRole.INDIVIDUAL.value,
                role_entity_id=None,
                plan_type=plan_type,
                source="funnel",
            ),
            automatic_tax={"enabled": auto_tax_enabled},
            idempotency_key=idem,
        )
    except Exception as e:
        logger.exception("public_sub_create_failed", extra={"email": body.email, "plan_code": body.plan_code})
        raise HTTPException(status_code=502, detail=f"Unable to start subscription: {str(e)}")

    latest_invoice = subscription.get("latest_invoice") or {}
    payment_intent = latest_invoice.get("payment_intent") or {}
    client_secret = payment_intent.get("client_secret")
    if not client_secret:
        raise HTTPException(status_code=502, detail="Missing client secret; unable to proceed with payment")

    # Optionally seed a status marker keyed by subscription id for visibility
    try:
        db = get_database()
        db.webhook_checkouts.update_one(
            {"subscription_id": subscription.get("id")},
            {"$setOnInsert": {
                "subscription_id": subscription.get("id"),
                "processed": False,
                "email": body.email,
                "inserted_at": __import__("datetime").datetime.utcnow(),
                "source": "funnel",
            }},
            upsert=True,
        )
    except Exception:
        pass

    logger.info("public_subscription_created", extra={"subscription_id": subscription.get("id"), "email": body.email, "plan_code": body.plan_code})
    return PublicCreateSubscriptionResponse(
        client_secret=client_secret,
        subscription_id=subscription.get("id"),
        customer_id=customer_id,
    )


# -----------------------------------------------------------------------------
# Payment status endpoint for Payment Element flow
# -----------------------------------------------------------------------------

@router.get("/stripe/payment-status", response_model=SessionStatusResponse)
async def get_payment_status(subscription_id: Optional[str] = Query(None), payment_intent: Optional[str] = Query(None)):
    """Return payment processing status for Payment Element-based subscriptions.

    processed = True when the Payment Intent succeeded or when the subscription is active/paid.
    """
    app_settings = get_app_settings()
    if not getattr(app_settings, "FUNNEL_PUBLIC_BILLING_ENABLED", True):
        raise HTTPException(status_code=404, detail="Not found")

    stripe = get_stripe()
    db = get_database()
    processed = False
    email = None
    user_status = None
    plan_assigned = None

    if payment_intent:
        try:
            pi = stripe.PaymentIntent.retrieve(payment_intent)
            processed = (pi.get("status") == "succeeded")
            if not email:
                email = (pi.get("charges", {}).get("data", [{}])[0].get("billing_details", {}).get("email") if pi.get("charges") else None)
        except Exception:
            pass

    if not processed and subscription_id:
        try:
            sub = stripe.Subscription.retrieve(subscription_id, expand=[
                "latest_invoice",
                "latest_invoice.customer",
                "latest_invoice.payment_intent",
            ])
            status_str = sub.get("status")
            latest_inv = sub.get("latest_invoice", {}) or {}
            pi_obj = latest_inv.get("payment_intent") or {}
            pi_status = pi_obj.get("status") if isinstance(pi_obj, dict) else None
            # Consider succeeded PI or paid invoice or active/trialing subscription as processed
            processed = (
                (pi_status == "succeeded")
                or (latest_inv.get("paid") is True)
                or (status_str in ("active", "trialing"))
            )
            if not email:
                cust = latest_inv.get("customer")
                if isinstance(cust, dict):
                    email = cust.get("email")
        except Exception:
            pass

    # If processed, derive user status/plan assigned similar to session-status
    if processed and email:
        user = db.users.find_one({"email": email}) or {}
        role_entity_id = user.get("role_entity_id")
        email_verified = bool(user.get("email_verified", False))
        user_status = "active" if email_verified else "pending_verification"
        if user.get("role") == UserRole.INDIVIDUAL.value and role_entity_id:
            plan_doc = db.plans.find_one({"individual_id": role_entity_id}) or {}
            plan_assigned = bool(plan_doc.get("status") in ("active", "pending", "past_due"))

    logger.info("payment_status", extra={"subscription_id": subscription_id, "payment_intent": payment_intent, "processed": processed, "email": email, "user_status": user_status, "plan_assigned": bool(plan_assigned)})
    return SessionStatusResponse(processed=processed, email=email, userStatus=user_status, planAssigned=plan_assigned)



@router.post("/otp/resend", status_code=status.HTTP_202_ACCEPTED)
async def resend_otp(body: ResendOTPRequest):
    """Public: resend signup OTP for funnel users. Feature-flagged."""
    app_settings = get_app_settings()
    if not getattr(app_settings, "FUNNEL_PUBLIC_BILLING_ENABLED", True):
        raise HTTPException(status_code=404, detail="Not found")

    auth = AuthController()
    user = auth.db.users.find_one({"email": body.email})
    if not user:
        # Webhook may be delayed; provision a minimal user+individual so OTP flow can proceed
        try:
            import uuid as _uuid
            from datetime import datetime as _dt
            individual_id = f"individual_{_uuid.uuid4().hex[:12]}"
            auth.db.individuals.insert_one({
                "id": individual_id,
                "name": body.email.split("@")[0],
                "email": body.email,
                "password_hash": "",
                "phone": "Not provided",
                "created_at": _dt.utcnow(),
                "updated_at": _dt.utcnow(),
                "onboarding_completed": False,
            })
            user_id = f"user_{_uuid.uuid4().hex[:12]}"
            auth.db.users.insert_one({
                "id": user_id,
                "email": body.email,
                "password_hash": "",
                "name": body.email.split("@")[0],
                "role": UserRole.INDIVIDUAL.value,
                "role_entity_id": individual_id,
                "department": None,
                "is_active": True,
                "email_verified": False,
                "created_at": _dt.utcnow(),
                "updated_at": _dt.utcnow(),
                "last_login": None,
            })
            user = {"id": user_id, "role_entity_id": individual_id}
            logger.info("provisional_user_created", extra={"email": body.email})
        except Exception as e:
            logger.exception("provisional_user_create_failed", extra={"email": body.email})
            raise HTTPException(status_code=500, detail="Unable to provision user for OTP")

    try:
        send_signup_otp(body.email, user.get("name"))
    except RuntimeError as e:
        # OTP rate limiting or SMTP errors
        logger.warning("otp_resend_failed", extra={"email": body.email, "error": str(e)})
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        logger.exception("otp_resend_error", extra={"email": body.email})
        raise HTTPException(status_code=500, detail="Unable to resend OTP")

    logger.info("otp_resent", extra={"email": body.email})
    return {"status": "otp_sent"}


@router.get("/debug/session/{session_id}")
async def debug_session_records(session_id: str):
    """Dev-only: return records linked to a checkout session to help verify persistence. Hidden from schema."""
    app_settings = get_app_settings()
    env = getattr(app_settings, "ENVIRONMENT", "development").lower()
    if env == "production":
        raise HTTPException(status_code=404, detail="Not found")
    db = get_database()
    out = {
        "webhook_checkouts": db.webhook_checkouts.find_one({"session_id": session_id}, {"_id": 0}) or {},
        "payments": db.payments.find_one({"stripe_checkout_session_id": session_id}, {"_id": 0}) or {},
    }
    # Try to locate plan via role_entity_id
    role_entity_id = out["webhook_checkouts"].get("role_entity_id") if out["webhook_checkouts"] else None
    if not role_entity_id and out["payments"]:
        role_entity_id = out["payments"].get("role_entity_id")
    plan = db.plans.find_one({"individual_id": role_entity_id}, {"_id": 0}) if role_entity_id else None
    out["plan"] = plan or {}
    return out
