try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:  # Fallback for pydantic <2
    from pydantic import BaseSettings  # type: ignore
    SettingsConfigDict = None  # type: ignore

from pydantic import Field
from functools import lru_cache
from typing import Optional

class StripeSettings(BaseSettings):
    """
    Canonical Stripe configuration for API Gateway.

    Important:
    - This is the SINGLE SOURCE OF TRUTH for all Stripe price IDs used by
      checkout sessions and webhook schedule creation. Do NOT hardcode price IDs
      anywhere else in the codebase. Consume them via get_settings().
    - Environment variables defined here should be the only ones you need to
      update across environments (dev/staging/prod).
    """

    STRIPE_SECRET_KEY: str = Field(..., env="STRIPE_SECRET_KEY")
    STRIPE_PUBLISHABLE_KEY: str = Field(..., env="STRIPE_PUBLISHABLE_KEY")
    STRIPE_WEBHOOK_SECRET: str = Field(..., env="STRIPE_WEBHOOK_SECRET")
    STRIPE_API_VERSION: str = Field("2023-10-16", env="STRIPE_API_VERSION")

   

    # Individual plans (month-based) - phased pricing using Subscription Schedules
    # New canonical envs (month naming)
    IND_1M_INTRO_MONTHLY: str = Field("", env="IND_1M_INTRO_MONTHLY")
    

    IND_1M_RECUR_MONTHLY: str = Field("", env="IND_1M_RECUR_MONTHLY")
    IND_3M_RECUR_MONTHLY: str = Field("", env="IND_3M_RECUR_MONTHLY")
    IND_6M_RECUR_MONTHLY: str = Field("", env="IND_6M_RECUR_MONTHLY")

    # New: Intro prices that bill per-period upfront (interval_count>1)
    # - 3-month upfront (quarterly) intro price, e.g., $49.99 every 3 months
    # - 6-month upfront (semiannual) intro price, e.g., $79.99 every 6 months
    IND_3M_INTRO_QUARTERLY: str = Field("", env="IND_3M_INTRO_QUARTERLY")
    IND_6M_INTRO_SEMIANNUAL: str = Field("", env="IND_6M_INTRO_SEMIANNUAL")


    SUCCESS_URL: str = Field("http://localhost:3000/stripe/success", env="STRIPE_SUCCESS_URL")
    CANCEL_URL: str = Field("http://localhost:3000/stripe/cancel", env="STRIPE_CANCEL_URL")

    # Allow unknown env vars so StripeSettings does not crash when
    # the global .env contains unrelated configuration keys.
    if SettingsConfigDict is not None:
        model_config = SettingsConfigDict(extra="allow", env_file=".env")
    else:
        class Config:
            extra = "allow"
            env_file = ".env"

@lru_cache()
def get_settings() -> StripeSettings:  # pragma: no cover
    return StripeSettings() 
