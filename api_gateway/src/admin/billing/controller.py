from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException


PLAN_PRICE_IDS = {
    "one_month": "IND_1M_INTRO_MONTHLY",
    "three_months": "IND_3M_INTRO_QUARTERLY",
    "six_months": "IND_6M_INTRO_SEMIANNUAL",
}


async def get_summary_controller(db, stripe) -> Dict[str, Any]:
    # Counts by plan type and status
    plan_counts: Dict[str, int] = {}
    active_counts: Dict[str, int] = {}
    total_active = 0
    for p in ["one_month", "three_months", "six_months"]:
        plan_counts[p] = db.plans.count_documents({"plan_type": p})
        active_counts[p] = db.plans.count_documents({"plan_type": p, "status": "active"})
        total_active += active_counts[p]

    # Try to compute MRR using Stripe prices; degrade gracefully
    mrr_by_plan: Dict[str, Optional[Dict[str, Any]]] = {}
    total_mrr = 0
    currency = "usd"
    for p, count in active_counts.items():
        price_attr = PLAN_PRICE_IDS.get(p)
        amount = None
        try:
            # Resolve price id from settings if available
            from ...stripe.config import get_settings
            settings = get_settings()
            price_id = getattr(settings, price_attr, None) if price_attr else None
            if price_id:
                price = stripe.Price.retrieve(price_id)
                unit = price.get("unit_amount") or price.get("unit_amount_decimal")
                currency = price.get("currency", currency)
                amount = (int(unit) / 100.0) if unit is not None else None
        except Exception:
            amount = None
        this_mrr = (amount * count) if (amount is not None) else None
        if this_mrr:
            total_mrr += this_mrr
        mrr_by_plan[p] = {"count": count, "price": amount, "mrr": this_mrr}

    arpu = (total_mrr / total_active) if total_active and total_mrr else None

    # Revenue trend last 3 months (best-effort from Stripe invoices)
    trend = []
    try:
        now = datetime.utcnow()
        for i in range(2, -1, -1):
            start = datetime(now.year, now.month, 1) - timedelta(days=30 * i)
            end = datetime(now.year, now.month, 1) - timedelta(days=30 * (i - 1)) if i != 0 else now
            invoices = stripe.Invoice.list(limit=100, created={"gte": int(start.timestamp()), "lte": int(end.timestamp())})
            total = 0
            for inv in getattr(invoices, "data", []) or []:
                amt = inv.get("amount_paid") or inv.get("total") or 0
                total += (amt / 100.0)
            trend.append({"start": start.isoformat(), "end": end.isoformat(), "total": total, "currency": currency})
    except Exception:
        trend = []

    return {
        "active_subscriptions": total_active,
        "mrr_by_plan": mrr_by_plan,
        "total_mrr": total_mrr if total_mrr else None,
        "currency": currency,
        "arpu": arpu,
        "trend_last_3_months": trend,
    }


async def list_subscriptions_controller(db, *, page: int, per_page: int, status: Optional[str]) -> Dict[str, Any]:
    filt: Dict[str, Any] = {}
    if status:
        filt["status"] = status
    skip = (page - 1) * per_page
    cursor = db.plans.find(filt).sort("updated_at", -1).skip(skip).limit(per_page)
    rows = []
    for doc in cursor:
        individual_id = doc.get("individual_id")
        user = db.users.find_one({"role_entity_id": individual_id}) or {}
        rows.append({
            "user": {"email": user.get("email"), "name": user.get("name")},
            "plan_type": doc.get("plan_type"),
            "status": doc.get("status"),
            "start_date": doc.get("created_at"),
            "next_billing_date": doc.get("current_period_end"),
            "subscription_id": doc.get("stripe_subscription_id"),
            "customer_id": doc.get("stripe_customer_id"),
        })
    total = db.plans.count_documents(filt)
    return {"page": page, "per_page": per_page, "total": total, "data": rows}


async def list_cancelled_controller(db, *, page: int, per_page: int) -> Dict[str, Any]:
    filt = {"status": "cancelled"}
    skip = (page - 1) * per_page
    cursor = db.plans.find(filt).sort("updated_at", -1).skip(skip).limit(per_page)
    rows = []
    for doc in cursor:
        individual_id = doc.get("individual_id")
        user = db.users.find_one({"role_entity_id": individual_id}) or {}
        rows.append({
            "user": {"email": user.get("email"), "name": user.get("name")},
            "plan_type": doc.get("plan_type"),
            "cancelled_at": doc.get("updated_at") or doc.get("current_period_end"),
            "reason": doc.get("cancellation_reason"),
        })
    total = db.plans.count_documents(filt)
    return {"page": page, "per_page": per_page, "total": total, "data": rows}


async def list_failed_payments_controller(db, *, page: int, per_page: int) -> Dict[str, Any]:
    # Look in audit for payment failures
    filt = {"event_type": {"$in": ["invoice.payment_failed", "charge.failed", "payment_intent.payment_failed"]}}
    skip = (page - 1) * per_page
    cursor = db.stripe_audit.find(filt).sort("created_at", -1).skip(skip).limit(per_page)
    rows = []
    for e in cursor:
        payload = e.get("payload") or {}
        customer_id = payload.get("customer") or payload.get("customer_id")
        individual_id = payload.get("role_entity_id") or payload.get("individual_id")
        user = db.users.find_one({"role_entity_id": individual_id}) or {}
        rows.append({
            "user": {"email": user.get("email"), "name": user.get("name")},
            "amount": (payload.get("amount_due") or payload.get("amount") or 0) / 100.0,
            "currency": payload.get("currency") or "usd",
            "reason": (e.get("status") or payload.get("failure_reason") or payload.get("error")),
            "date": e.get("created_at"),
            "customer_id": customer_id,
        })
    total = db.stripe_audit.count_documents(filt)
    return {"page": page, "per_page": per_page, "total": total, "data": rows}
