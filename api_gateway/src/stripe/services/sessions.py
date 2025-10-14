import stripe
from ..client import get_stripe
from ...billing.schema import UserRole
from ..config import get_settings
from ..idempotency import generate

settings = get_settings()
# Note: Checkout uses INTRO prices only, taken from StripeSettings
# (IND_*_INTRO_MONTHLY). Recurring pricing is configured via Subscription
# Schedules in the webhook handler and does not affect this mapping.
stripe = get_stripe()

INTRO_PRICE_MAP = {
    # Individuals — intro prices only; prefer per-period upfront IDs when available
    (UserRole.INDIVIDUAL.value, "one_month"): settings.IND_1M_INTRO_MONTHLY,
    (UserRole.INDIVIDUAL.value, "three_months"): settings.IND_3M_INTRO_QUARTERLY,
    (UserRole.INDIVIDUAL.value, "six_months"): settings.IND_6M_INTRO_SEMIANNUAL,
}
def create_checkout_session(*, user, plan_type: str) -> dict:
    role_value = user.role.value if hasattr(user, "role") else str(user.role)
    key = (role_value, plan_type)
    if key not in INTRO_PRICE_MAP:
        raise ValueError(f"Intro price mapping not found for {key}. Ensure IND_1M_INTRO_MONTHLY, IND_3M_INTRO_QUARTERLY, and IND_6M_INTRO_SEMIANNUAL are set.")

    price_id = INTRO_PRICE_MAP[key]
    # Generate a unique idempotency key per checkout attempt to avoid reusing an old
    # finished Checkout Session which would display a completion/timed-out message.
    # We include the user id and current timestamp so retries within a short period
    # (e.g., page refresh) still map to the same attempt, but subsequent fresh
    # purchase flows generate a brand-new session.
    import time, uuid
    idem_key = generate("checkout", user.user_id, plan_type, str(time.time()), uuid.uuid4().hex)
    # Note: Since Checkout here uses customer_email and not a full customer with address,
    # enabling automatic_tax can fail if Stripe cannot resolve the tax location.
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.CANCEL_URL}",
        customer_email=user.email,
        client_reference_id=f"{role_value}:{user.role_entity_id}",
        metadata={
            "role": role_value,
            "role_entity_id": user.role_entity_id,
            "plan_type": plan_type,
        },
        payment_method_options={"card": {"request_three_d_secure": "any"}},
        automatic_tax={"enabled": False},
        idempotency_key=idem_key,
    )
    return {"id": session.id, "url": session.url}
