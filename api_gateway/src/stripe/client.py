import stripe
from functools import lru_cache
from .config import get_settings

@lru_cache()
def get_stripe() -> stripe:  # pragma: no cover
    settings = get_settings()
    stripe.api_key = settings.STRIPE_SECRET_KEY
    stripe.api_version = settings.STRIPE_API_VERSION
    stripe.max_network_retries = 2
    stripe.enable_telemetry = False
    return stripe 
