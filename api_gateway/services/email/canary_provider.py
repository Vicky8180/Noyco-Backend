from __future__ import annotations

import hashlib
from typing import Iterable, Optional, Tuple

from .email_provider import EmailProvider, SendResult


def _bucket_from_email(email: str) -> int:
    h = hashlib.sha256((email or "").encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 100


class CanaryProvider(EmailProvider):
    """Routes a percentage of sends to secondary provider based on recipient hash.

    Primary: typically MailerLite
    Secondary: typically MailerSend
    percent: 0-100 (percentage of emails routed to secondary)
    """

    def __init__(self, *, primary: EmailProvider, secondary: EmailProvider, percent: int) -> None:
        self.primary = primary
        self.secondary = secondary
        self.percent = max(0, min(100, int(percent)))

    def _choose(self, to_email: str) -> EmailProvider:
        if self.percent <= 0:
            return self.primary
        if self.percent >= 100:
            return self.secondary
        bucket = _bucket_from_email(to_email)
        return self.secondary if bucket < self.percent else self.primary

    def send_email(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> SendResult:
        provider = self._choose(to)
        return provider.send_email(
            to=to,
            subject=subject,
            html=html,
            text=text,
            from_email=from_email,
            from_name=from_name,
        )

    def send_bulk(
        self,
        *,
        recipients: Iterable[Tuple[str, str]],
        subject: str,
        html: str,
        text: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> SendResult:
        # For deterministic behavior, route each email individually.
        last: Optional[SendResult] = None
        for email, name in recipients:
            res = self.send_email(
                to=email,
                subject=subject,
                html=html,
                text=text,
                from_email=from_email,
                from_name=from_name,
            )
            last = res
            if not res.ok:
                return res
        return last or SendResult(ok=True, provider="canary")
