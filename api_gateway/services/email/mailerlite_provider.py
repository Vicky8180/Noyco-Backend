from __future__ import annotations
import json
from typing import Iterable, Optional, Tuple

import httpx

from .email_provider import EmailProvider, SendResult

MAILERLITE_API_BASE = "https://connect.mailerlite.com/api"

class MailerLiteProvider(EmailProvider):
    def __init__(self, *, api_key: Optional[str], default_from: Optional[str], default_from_name: Optional[str]) -> None:
        self.api_key = api_key
        self.default_from = default_from
        self.default_from_name = default_from_name

    def _client(self) -> httpx.Client:
        headers = {
            "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        return httpx.Client(base_url=MAILERLITE_API_BASE, headers=headers, timeout=20.0)

    def _send(self, *, to: str, subject: str, html: str, text: Optional[str], from_email: Optional[str], from_name: Optional[str]) -> SendResult:
        if not self.api_key:
            return SendResult(ok=False, provider="mailerlite", error="Missing MAILERLITE_API_KEY")
        from_email = from_email or self.default_from
        from_name = from_name or self.default_from_name
        if not from_email:
            return SendResult(ok=False, provider="mailerlite", error="Missing from email")

        payload = {
            "subject": subject,
            "from": {"email": from_email, "name": from_name or ""},
            "content": [
                {"type": "text/html", "value": html},
            ]
        }
        # MailerLite requires recipients via path or template campaigns; we'll use transactional endpoint if available.
        # As a general approach, we use a generic endpoint "emails/send"; adjust to your MailerLite plan.
        # Reference: https://developers.mailerlite.com/
        data = {
            "to": [{"email": to}],
            **payload,
        }
        try:
            with self._client() as client:
                # Endpoint name may vary by plan: transactional emails are often /api/v2/email/send or similar.
                # We'll use a commonly documented v2 style; adapt during integration if needed.
                resp = client.post("/v2/email/send", content=json.dumps(data))
                if resp.status_code >= 200 and resp.status_code < 300:
                    body = resp.json()
                    message_id = body.get("message_id") or body.get("id")
                    return SendResult(ok=True, provider="mailerlite", message_id=message_id)
                else:
                    return SendResult(ok=False, provider="mailerlite", error=f"HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            return SendResult(ok=False, provider="mailerlite", error=str(e))

    def send_email(self, *, to: str, subject: str, html: str, text: Optional[str] = None, from_email: Optional[str] = None, from_name: Optional[str] = None) -> SendResult:
        return self._send(to=to, subject=subject, html=html, text=text, from_email=from_email, from_name=from_name)

    def send_bulk(self, *, recipients: Iterable[Tuple[str, str]], subject: str, html: str, text: Optional[str] = None, from_email: Optional[str] = None, from_name: Optional[str] = None) -> SendResult:
        # Basic implementation: iterate and send individually; for scale, implement ML bulk endpoint/campaign
        last_result: Optional[SendResult] = None
        for email, _name in recipients:
            last_result = self.send_email(to=email, subject=subject, html=html, text=text, from_email=from_email, from_name=from_name)
            if not last_result.ok:
                return last_result
        return last_result or SendResult(ok=True, provider="mailerlite")
