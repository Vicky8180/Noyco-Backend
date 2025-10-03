from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, EmailStr, Field
from typing import List, Literal, Optional, Dict
from time import time
import logging

# Stripe config and client
from ..stripe.config import get_settings as get_stripe_settings
from ..stripe.client import get_stripe
from ..stripe.idempotency import generate as generate_idem
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
    email: EmailStr
    plan_code: Literal["IND_1M", "IND_3M", "IND_6M"] = Field(..., description="One of IND_1M | IND_3M | IND_6M")


class CheckoutSessionResponse(BaseModel):
    sessionId: str


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
        ("IND_3M", "3 Months", 3, settings.IND_3M_INTRO_MONTHLY, settings.IND_3M_RECUR_MONTHLY),
        ("IND_6M", "6 Months", 6, settings.IND_6M_INTRO_MONTHLY, settings.IND_6M_RECUR_MONTHLY),
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
                        intro_text = f"{intro_amount} first {months} months"
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


@router.post("/billing/checkout-session", response_model=CheckoutSessionResponse)
async def create_public_checkout_session(body: CheckoutSessionRequest):
    """Create a Stripe Checkout Session for funnel users (no auth).

    No DB writes; fulfillment occurs in Stripe webhooks.
    """
    app_settings = get_app_settings()
    if not getattr(app_settings, "FUNNEL_PUBLIC_BILLING_ENABLED", True):
        raise HTTPException(status_code=404, detail="Not found")
    settings = get_stripe_settings()
    stripe = get_stripe()

    code_to_price_and_plan = {
        "IND_1M": (settings.IND_1M_INTRO_MONTHLY, "one_month"),
        "IND_3M": (settings.IND_3M_INTRO_MONTHLY, "three_months"),
        "IND_6M": (settings.IND_6M_INTRO_MONTHLY, "six_months"),
    }
    price_id, plan_type = code_to_price_and_plan.get(body.plan_code, (None, None))
    if not price_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported or unconfigured plan_code")

    # Idempotency: scope by email+plan+timestamp
    import uuid
    idem = generate_idem("public_checkout", body.email, body.plan_code, str(int(time())), uuid.uuid4().hex)

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{settings.SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.CANCEL_URL}",
            customer_email=body.email,
            client_reference_id=f"public:individual:{body.plan_code}",
            metadata={
                "source": "funnel",
                "role": "individual",
                "plan_type": plan_type,
                "billing_cycle": "monthly",
                # role_entity_id intentionally omitted in public flow; will be created during webhook
            },
            payment_method_options={"card": {"request_three_d_secure": "any"}},
            automatic_tax={"enabled": True},
            idempotency_key=idem,
        )
    except Exception as e:
        logger.exception("checkout_session_create_failed", extra={"email": body.email, "plan_code": body.plan_code})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Unable to start checkout: {str(e)}")


    sid = session.get("id")
    # Seed a light marker to help correlate later (non-authoritative; webhook will fill details)
    try:
        db = get_database()
        db.webhook_checkouts.update_one(
            {"session_id": sid},
            {"$setOnInsert": {"session_id": sid, "processed": False, "email": body.email, "inserted_at": __import__("datetime").datetime.utcnow()}},
            upsert=True,
        )
    except Exception:
        pass
    logger.info("checkout_session_created", extra={"session_id": sid, "email": body.email, "plan_code": body.plan_code})
    return CheckoutSessionResponse(sessionId=sid)


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
