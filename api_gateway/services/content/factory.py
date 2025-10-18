from __future__ import annotations
from typing import Optional

from api_gateway.config import get_settings
from .content_provider import ContentProvider
from .metrics_existing_provider import MetricsContentProviderExisting

_provider_singleton: Optional[ContentProvider] = None

def get_content_provider() -> ContentProvider:
    global _provider_singleton
    if _provider_singleton is not None:
        return _provider_singleton

    settings = get_settings()
    key = (settings.CONTENT_PROVIDER or "metrics_existing").lower()

    if key == "metrics_existing":
        _provider_singleton = MetricsContentProviderExisting()
    else:
        # Default to metrics existing for now
        _provider_singleton = MetricsContentProviderExisting()

    return _provider_singleton
