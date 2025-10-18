from __future__ import annotations
import json
from typing import Iterable, Optional, Tuple, List, Dict

import httpx

from .email_provider import EmailProvider, SendResult

MAILERSEND_API_BASE = "https://api.mailersend.com/v1"


class MailerSendProvider(EmailProvider):
    """MailerSend transactional email provider adapter.

    Implements the EmailProvider interface using MailerSend's v1/email endpoint.
    All errors are captured and returned via SendResult without raising exceptions.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str],
        default_from: Optional[str],
        default_from_name: Optional[str],
    ) -> None:
        self.api_key = api_key
        self.default_from = default_from
        self.default_from_name = default_from_name

    def _client(self) -> httpx.Client:
        headers = {
            "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        return httpx.Client(base_url=MAILERSEND_API_BASE, headers=headers, timeout=20.0)

    @staticmethod
    def _normalize_to_single(email: str, name: Optional[str] = None) -> List[Dict[str, str]]:
        return [{"email": email, **({"name": name} if name else {})}]

    @staticmethod
    def _normalize_to_bulk(recipients: Iterable[Tuple[str, str]]) -> List[Dict[str, str]]:
        to_list: List[Dict[str, str]] = []
        for email, name in recipients:
            if email:
                item: Dict[str, str] = {"email": email}
                if name:
                    item["name"] = name
                to_list.append(item)
        return to_list

    @staticmethod
    def _parse_error(resp: httpx.Response) -> str:
        try:
            data = resp.json()
            # Common fields in MailerSend errors: { "message": "...", "errors": { ... } }
            if isinstance(data, dict):
                if "message" in data and isinstance(data["message"], str):
                    return f"HTTP {resp.status_code}: {data['message']}"
                if "errors" in data:
                    return f"HTTP {resp.status_code}: {json.dumps(data['errors'])}"
            return f"HTTP {resp.status_code}: {resp.text}"
        except Exception:
            return f"HTTP {resp.status_code}: {resp.text}"

    def _post_email(self, payload: dict) -> SendResult:
        if not self.api_key:
            return SendResult(ok=False, provider="mailersend", error="Missing MAILERSEND_API_KEY")

        # Validate from
        from_email = payload.get("from", {}).get("email")
        if not from_email:
            return SendResult(ok=False, provider="mailersend", error="Missing from email")

        try:
            with self._client() as client:
                resp = client.post("/email", content=json.dumps(payload))
                if 200 <= resp.status_code < 300:
                    # MailerSend often returns 202 Accepted with x-message-id header
                    message_id = resp.headers.get("x-message-id")
                    if not message_id:
                        # Try body as fallback
                        try:
                            body = resp.json()
                            if isinstance(body, dict):
                                message_id = body.get("message_id") or body.get("id")
                        except Exception:
                            message_id = None
                    return SendResult(ok=True, provider="mailersend", message_id=message_id)
                else:
                    return SendResult(ok=False, provider="mailersend", error=self._parse_error(resp))
        except Exception as e:
            return SendResult(ok=False, provider="mailersend", error=str(e))

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
        from_email = from_email or self.default_from
        from_name = from_name or self.default_from_name

        payload = {
            "from": {"email": from_email or "", "name": from_name or ""},
            "to": self._normalize_to_single(to),
            "subject": subject,
            "html": html,
        }
        if text:
            payload["text"] = text

        return self._post_email(payload)

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
        from_email = from_email or self.default_from
        from_name = from_name or self.default_from_name

        to_list = self._normalize_to_bulk(recipients)
        if not to_list:
            return SendResult(ok=False, provider="mailersend", error="No recipients provided")

        payload = {
            "from": {"email": from_email or "", "name": from_name or ""},
            "to": to_list,
            "subject": subject,
            "html": html,
        }
        if text:
            payload["text"] = text

        return self._post_email(payload)
