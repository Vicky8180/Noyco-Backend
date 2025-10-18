from __future__ import annotations
from typing import Iterable, Optional, Tuple

from .email_provider import EmailProvider, SendResult

class NullProvider(EmailProvider):
    """No-op provider for local/dev or when EMAIL_PROVIDER=none. Always returns ok=True.
    Useful to avoid errors when keys are not configured.
    """

    def send_email(self, *, to: str, subject: str, html: str, text: Optional[str] = None, from_email: Optional[str] = None, from_name: Optional[str] = None) -> SendResult:
        return SendResult(ok=True, provider="none", message_id="noop")

    def send_bulk(self, *, recipients: Iterable[Tuple[str, str]], subject: str, html: str, text: Optional[str] = None, from_email: Optional[str] = None, from_name: Optional[str] = None) -> SendResult:
        return SendResult(ok=True, provider="none", message_id="noop-bulk")
