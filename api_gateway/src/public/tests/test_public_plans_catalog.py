import types
from fastapi.testclient import TestClient

from ....main import app

client = TestClient(app)


def test_public_plans_display_uses_total_for_multi_months(monkeypatch):
    # Patch Stripe settings to provide specific price IDs
    from .. import routes as public_routes

    class S:
        IND_1M_INTRO_MONTHLY = "price_intro_1m"
        IND_1M_RECUR_MONTHLY = "price_recur_1m"
        IND_3M_INTRO_QUARTERLY = "price_intro_3m_q"
        IND_3M_INTRO_MONTHLY = "price_intro_3m_legacy"
        IND_3M_RECUR_MONTHLY = "price_recur_3m"
        IND_6M_INTRO_SEMIANNUAL = "price_intro_6m_sa"
        IND_6M_INTRO_MONTHLY = "price_intro_6m_legacy"
        IND_6M_RECUR_MONTHLY = "price_recur_6m"

    monkeypatch.setattr(public_routes, "get_stripe_settings", lambda: S())

    # Fake Stripe client returning expected prices
    class FakeStripe:
        class Price:
            @staticmethod
            def retrieve(price_id):
                # Map IDs to amounts
                mapping = {
                    "price_intro_1m": {"unit_amount": 1999, "currency": "usd"},
                    "price_recur_1m": {"unit_amount": 2999, "currency": "usd"},
                    "price_intro_3m_q": {"unit_amount": 4999, "currency": "usd"},
                    "price_recur_3m": {"unit_amount": 2999, "currency": "usd"},
                    "price_intro_6m_sa": {"unit_amount": 7999, "currency": "usd"},
                    "price_recur_6m": {"unit_amount": 2999, "currency": "usd"},
                }
                return mapping.get(price_id, {"unit_amount": 0, "currency": "usd"})

    monkeypatch.setattr(public_routes, "get_stripe", lambda: FakeStripe)

    # Clear the small TTL cache to avoid stale values
    public_routes._PLANS_CACHE["value"] = None
    public_routes._PLANS_CACHE["ts"] = 0.0

    resp = client.get("/public/billing/plans")
    assert resp.status_code == 200
    data = resp.json()
    plans = {p["code"]: p for p in data["plans"]}

    assert plans["IND_1M"]["introDisplay"] == "$19.99 first month"
    assert plans["IND_1M"]["recurringDisplay"] == "then $29.99 every 1 month"

    assert plans["IND_3M"]["introDisplay"] == "$49.99 total for first 3 months"
    assert plans["IND_3M"]["recurringDisplay"] == "then $29.99 every 1 month"

    assert plans["IND_6M"]["introDisplay"] == "$79.99 total for first 6 months"
    assert plans["IND_6M"]["recurringDisplay"] == "then $29.99 every 1 month"
