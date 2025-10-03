import stripe
from fastapi import Request, HTTPException, status
from ..client import get_stripe
from ..config import get_settings
from ..idempotency import is_processed, mark_processed
from ..audit import log

stripe = get_stripe()
settings = get_settings()

async def verify_stripe_signature(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid signature: {e}")

    # replay protection
        # replay protection handled in dispatcher; do not short-circuit here to keep handler fast
        return event
    return event 
