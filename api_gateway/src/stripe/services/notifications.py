from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any

# Use absolute imports to reference the top-level API Gateway config and database
from api_gateway.config import get_settings
from api_gateway.database.db import get_database
from ...auth.email_service import _send_email
from .templates import render_templates
from ..audit import log
from pymongo.errors import DuplicateKeyError


settings = get_settings()
db = get_database()


def _fmt_amount(amount_cents: int, currency: str) -> str:
    try:
        return f"{amount_cents/100:.2f}"
    except Exception:
        return str(amount_cents)


def get_recipient_email(stripe_obj: Dict[str, Any], fallback: Optional[str] = None) -> Optional[str]:
    # Try invoice.customer_email first
    email = None
    if stripe_obj:
        email = stripe_obj.get("customer_email") or stripe_obj.get("email")

        # If not found, try retrieving customer from DB via Stripe customer id
        customer_id = stripe_obj.get("customer") or stripe_obj.get("customer_id")
        if not email and customer_id:
            # Attempt lookups in common collections
            for coll_name in ("users", "individuals"):
                doc = db[coll_name].find_one({"stripe_customer_id": customer_id})
                if not doc:
                    doc = db[coll_name].find_one({"stripe.customer_id": customer_id})
                if doc and doc.get("email"):
                    email = doc["email"]
                    break

    return email or fallback


def _common_vars(base: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **base,
        "manageBillingUrl": getattr(settings, "MANAGE_BILLING_URL", "https://app.noyco.com/billing"),
        "supportEmail": getattr(settings, "SUPPORT_EMAIL", "support@noyco.com"),
    }


def _email_events_collection():
    col = db["stripe_email_events"]
    try:
        col.create_index([("stripe_event_id", 1), ("email_type", 1)], unique=True)
    except Exception:
        pass
    return col


def _send_notification(event_key: str, subject: str, to_email: Optional[str], vars: Dict[str, Any], *, event_id: Optional[str] = None) -> None:
    # Feature flag guard
    if not getattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True):
        try:
            log("email_notifications_disabled", {"email_type": event_key, "event_id": event_id}, "ok", "skipped")
        except Exception:
            pass
        return
    # Recipient guard
    if not to_email:
        try:
            log("email_recipient_missing", {"email_type": event_key, "event_id": event_id}, "ok", "skipped")
        except Exception:
            pass
        return

    col = _email_events_collection()
    now = datetime.utcnow()

    # Attempt to insert a pending record for idempotency
    if event_id:
        try:
            col.insert_one({
                "stripe_event_id": event_id,
                "email_type": event_key,
                "status": "pending",
                "to": to_email,
                "subject": subject,
                "createdAt": now,
                "updatedAt": now,
            })
        except DuplicateKeyError:
            # Already handled
            return
        except Exception as e:
            # Non-fatal: continue but note in logs
            try:
                log("email_idempotency_insert", {"event_id": event_id, "email_type": event_key}, "error", str(e))
            except Exception:
                pass

    try:
        rendered = render_templates(event_key, vars)
        text = rendered["text"]
        html = rendered.get("html")

        # BCC handled inside _send_email via settings default
        _send_email(to_email, subject, text, html_body=html)
        try:
            log("email_notification_sent", {"email_type": event_key, "to": to_email, "event_id": event_id}, "ok", subject)
        except Exception:
            pass

        if event_id:
            try:
                col.update_one({"stripe_event_id": event_id, "email_type": event_key}, {"$set": {"status": "sent", "updatedAt": datetime.utcnow()}})
            except Exception:
                pass
    except Exception as e:
        # Record failure but do not raise to keep webhook fast-ACK
        if event_id:
            try:
                col.update_one({"stripe_event_id": event_id, "email_type": event_key}, {"$set": {"status": "failed", "error": str(e), "updatedAt": datetime.utcnow()}})
            except Exception:
                pass
        try:
            log("email_notification", {"event_id": event_id, "email_type": event_key}, "error", str(e))
        except Exception:
            pass
        return


# ───────────── Invoice Notifications ─────────────

def send_invoice_paid(event: Dict[str, Any], invoice: Dict[str, Any], customer: Optional[Dict[str, Any]] = None) -> None:
    to_email = get_recipient_email(invoice, fallback=(customer or {}).get("email"))
    amount = _fmt_amount(invoice.get("amount_paid", 0), invoice.get("currency", ""))
    # Extract hosted invoice URL and billing details from first line
    # Prefer hosted invoice link, then PDF as a fallback, then manage billing URL as last resort
    hosted_url = (
        invoice.get("hosted_invoice_url")
        or invoice.get("invoice_pdf")
        or getattr(settings, "MANAGE_BILLING_URL", "https://app.noyco.com/billing")
    )
    line = None
    try:
        lines = (invoice.get("lines", {}) or {}).get("data", [])
        line = lines[0] if lines else None
    except Exception:
        line = None
    price = (line.get("price") if isinstance(line, dict) else None) or {}
    recurring = (price.get("recurring") or {}) if isinstance(price, dict) else {}
    unit_amount = price.get("unit_amount") if isinstance(price, dict) else None
    unit_price = _fmt_amount(unit_amount, invoice.get("currency", "")) if unit_amount is not None else "N/A"
    quantity = (line.get("quantity") if isinstance(line, dict) else None) or 1
    interval = recurring.get("interval") or "period"
    interval_count = recurring.get("interval_count") or 1

    vars = _common_vars({
        "customerName": (customer or {}).get("name", ""),
        "invoiceDate": _safe_date(invoice.get("created")),
        "amount": amount,
        "currency": (invoice.get("currency") or "").upper(),
        "plan": _plan_name_from_invoice(invoice) or "",
        "periodStart": _period_date(invoice, "period_start"),
        "periodEnd": _period_date(invoice, "period_end"),
        # New details
        "hostedInvoiceUrl": hosted_url,
        "unitPrice": unit_price,
        "quantity": quantity,
        "interval": interval,
        "intervalCount": interval_count,
    })
    subject = "Payment received — thank you!"
    _send_notification("invoice_paid", subject, to_email, vars, event_id=event.get("id"))


def send_invoice_failed(event: Dict[str, Any], invoice: Dict[str, Any], customer: Optional[Dict[str, Any]] = None) -> None:
    to_email = get_recipient_email(invoice, fallback=(customer or {}).get("email"))
    amount = _fmt_amount(invoice.get("amount_due", 0), invoice.get("currency", ""))
    vars = _common_vars({
        "customerName": (customer or {}).get("name", ""),
        "invoiceDate": _safe_date(invoice.get("created")),
        "amount": amount,
        "currency": (invoice.get("currency") or "").upper(),
        "plan": _plan_name_from_invoice(invoice) or "",
        "dueDate": _safe_date(invoice.get("due_date")),
    })
    subject = "We couldn't process your payment"
    _send_notification("invoice_failed", subject, to_email, vars, event_id=event.get("id"))


def send_invoice_upcoming(event: Dict[str, Any], upcoming_invoice: Dict[str, Any], customer: Optional[Dict[str, Any]] = None) -> None:
    to_email = get_recipient_email(upcoming_invoice, fallback=(customer or {}).get("email"))
    amount = _fmt_amount(upcoming_invoice.get("amount_due", 0), upcoming_invoice.get("currency", ""))
    vars = _common_vars({
        "customerName": (customer or {}).get("name", ""),
        "invoiceDate": _safe_date(upcoming_invoice.get("created")),
        "amount": amount,
        "currency": (upcoming_invoice.get("currency") or "").upper(),
        "plan": _plan_name_from_invoice(upcoming_invoice) or "",
        "periodStart": _period_date(upcoming_invoice, "period_start"),
        "periodEnd": _period_date(upcoming_invoice, "period_end"),
    })
    subject = "Upcoming invoice"
    _send_notification("invoice_upcoming", subject, to_email, vars, event_id=event.get("id"))


# ───────────── Subscription Notifications ─────────────

def send_subscription_started(event: Dict[str, Any], subscription: Dict[str, Any], customer: Optional[Dict[str, Any]] = None) -> None:
    to_email = get_recipient_email(subscription, fallback=(customer or {}).get("email"))
    vars = _common_vars({
        "customerName": (customer or {}).get("name", ""),
        "plan": _plan_name_from_subscription(subscription) or "",
        "periodStart": _safe_date(subscription.get("current_period_start")),
        "periodEnd": _safe_date(subscription.get("current_period_end")),
    })
    subject = "Your subscription has started"
    _send_notification("subscription_started", subject, to_email, vars, event_id=event.get("id"))


def send_subscription_updated(event: Dict[str, Any], subscription: Dict[str, Any], customer: Optional[Dict[str, Any]] = None) -> None:
    to_email = get_recipient_email(subscription, fallback=(customer or {}).get("email"))
    vars = _common_vars({
        "customerName": (customer or {}).get("name", ""),
        "plan": _plan_name_from_subscription(subscription) or "",
        "periodStart": _safe_date(subscription.get("current_period_start")),
        "periodEnd": _safe_date(subscription.get("current_period_end")),
    })
    subject = "Your subscription has been updated"
    _send_notification("subscription_updated", subject, to_email, vars, event_id=event.get("id"))


def send_subscription_canceled(event: Dict[str, Any], subscription: Dict[str, Any], customer: Optional[Dict[str, Any]] = None) -> None:
    to_email = get_recipient_email(subscription, fallback=(customer or {}).get("email"))
    vars = _common_vars({
        "customerName": (customer or {}).get("name", ""),
        "plan": _plan_name_from_subscription(subscription) or "",
        "periodEnd": _safe_date(subscription.get("current_period_end")),
    })
    subject = "Your subscription has been canceled"
    _send_notification("subscription_canceled", subject, to_email, vars, event_id=event.get("id"))


# ───────────── Helpers ─────────────

def _safe_date(ts: Optional[int]) -> str:
    if not ts:
        return ""
    try:
        return datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _period_date(invoice_like: Dict[str, Any], key: str) -> str:
    # Try lines.data[0].period[key]
    try:
        lines = invoice_like.get("lines", {}).get("data", [])
        if lines:
            period = lines[0].get("period", {})
            return _safe_date(period.get(key))
    except Exception:
        pass
    return ""


def _plan_name_from_invoice(invoice: Dict[str, Any]) -> Optional[str]:
    try:
        lines = invoice.get("lines", {}).get("data", [])
        if lines:
            price = (lines[0].get("price") or {})
            # Prefer nickname, fallback to product id
            return price.get("nickname") or price.get("id")
    except Exception:
        pass
    return None


def _plan_name_from_subscription(sub: Dict[str, Any]) -> Optional[str]:
    try:
        items = sub.get("items", {}).get("data", [])
        if items:
            price = (items[0].get("price") or {})
            return price.get("nickname") or price.get("id")
    except Exception:
        pass
    return None
