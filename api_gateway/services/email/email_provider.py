from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Optional, Protocol, Tuple

@dataclass
class SendResult:
    ok: bool
    provider: str
    message_id: Optional[str] = None
    error: Optional[str] = None

class EmailProvider(Protocol):
    """Pluggable email provider interface.

    Implementations should raise no exceptions on send; instead return SendResult with ok=False and error populated.
    """

    def send_email(self, *, to: str, subject: str, html: str, text: Optional[str] = None, from_email: Optional[str] = None, from_name: Optional[str] = None) -> SendResult:
        ...

    def send_bulk(self, *, recipients: Iterable[Tuple[str, str]], subject: str, html: str, text: Optional[str] = None, from_email: Optional[str] = None, from_name: Optional[str] = None) -> SendResult:
        """Optional: recipients is iterable of tuples (email, display_name)."""
        ...
