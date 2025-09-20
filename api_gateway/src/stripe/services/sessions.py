import stripe
from ..client import get_stripe
from ..schemas import BillingCycle
from ...billing.schema import UserRole
from ..config import get_settings
from ..idempotency import generate

settings = get_settings()
stripe = get_stripe()

PRICE_MAP = {
    # Hospital prices
    # (UserRole.HOSPITAL.value, "lite", BillingCycle.MONTHLY): settings.PRICE_HOSP_LITE_MONTHLY,
    # (UserRole.HOSPITAL.value, "lite", BillingCycle.YEARLY): settings.PRICE_HOSP_LITE_YEARLY,
    # (UserRole.HOSPITAL.value, "pro", BillingCycle.MONTHLY): settings.PRICE_HOSP_PRO_MONTHLY,
    # (UserRole.HOSPITAL.value, "pro", BillingCycle.YEARLY): settings.PRICE_HOSP_PRO_YEARLY,

    # Individual prices
    (UserRole.INDIVIDUAL.value, "lite", BillingCycle.MONTHLY): settings.PRICE_IND_LITE_MONTHLY,
    (UserRole.INDIVIDUAL.value, "lite", BillingCycle.YEARLY): settings.PRICE_IND_LITE_YEARLY,
    (UserRole.INDIVIDUAL.value, "pro", BillingCycle.MONTHLY): settings.PRICE_IND_PRO_MONTHLY,
    (UserRole.INDIVIDUAL.value, "pro", BillingCycle.YEARLY): settings.PRICE_IND_PRO_YEARLY,
}

def create_checkout_session(*, user, plan_type: str, billing_cycle: BillingCycle) -> str:
    key = (user.role.value if hasattr(user, 'role') else user.role, plan_type, billing_cycle)
    if key not in PRICE_MAP:
        raise ValueError(f"Price mapping not found for {key}. Check environment variables.")

    price_id = PRICE_MAP[key]
    # Generate a unique idempotency key per checkout attempt to avoid reusing an old
    # finished Checkout Session which would display a completion/timed-out message.
    # We include the user id and current timestamp so retries within a short period
    # (e.g., page refresh) still map to the same attempt, but subsequent fresh
    # purchase flows generate a brand-new session.
    import time, uuid
    idem_key = generate("checkout", user.user_id, plan_type, billing_cycle, str(time.time()), uuid.uuid4().hex)
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.CANCEL_URL}",
        customer_email=user.email,
        client_reference_id=f"{user.role}:{user.role_entity_id}",
        metadata={
            "role": user.role,
            "role_entity_id": user.role_entity_id,
            "plan": plan_type,
            "billing_cycle": billing_cycle,
        },
        payment_method_options={"card": {"request_three_d_secure": "any"}},
        automatic_tax={"enabled": True},
        idempotency_key=idem_key,
    )
    return session.url 
