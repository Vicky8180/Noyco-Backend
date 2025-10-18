from __future__ import annotations
from typing import Optional, Tuple, Iterable
import hashlib

from api_gateway.config import get_settings
from .email_provider import EmailProvider
from .mailerlite_provider import MailerLiteProvider
from .mailersend_provider import MailerSendProvider
from .canary_provider import CanaryProvider

_provider_singleton: Optional[EmailProvider] = None

def _create_mailerlite(settings) -> EmailProvider:
    return MailerLiteProvider(
        api_key=settings.MAILERLITE_API_KEY,
        default_from=settings.EMAIL_FROM,
        default_from_name=settings.EMAIL_FROM_NAME,
    )


def _create_mailersend(settings) -> EmailProvider:
    return MailerSendProvider(
        api_key=getattr(settings, "MAILERSEND_API_KEY", None),
        default_from=getattr(settings, "MAILERSEND_FROM", None) or settings.EMAIL_FROM,
        default_from_name=getattr(settings, "MAILERSEND_FROM_NAME", None) or settings.EMAIL_FROM_NAME,
    )


def _deterministic_bucket(key: str) -> int:
    """Hash a key into a bucket [0..99] for percentage-based routing."""
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    # Use first 8 hex chars -> int -> mod 100
    return int(h[:8], 16) % 100


def get_email_provider() -> EmailProvider:
    global _provider_singleton
    if _provider_singleton is not None:
        return _provider_singleton

    settings = get_settings()
    provider_key = (settings.EMAIL_PROVIDER or "none").lower()

    if provider_key == "mailerlite":
        _provider_singleton = _create_mailerlite(settings)
    elif provider_key == "mailersend":
        _provider_singleton = _create_mailersend(settings)
    elif provider_key == "canary":
        percent = max(0, min(100, int(getattr(settings, "MAILERSEND_PERCENT", 0))))
        _provider_singleton = CanaryProvider(
            primary=_create_mailerlite(settings),
            secondary=_create_mailersend(settings),
            percent=percent,
        )
    else:
        from .null_provider import NullProvider
        _provider_singleton = NullProvider()

    return _provider_singleton
