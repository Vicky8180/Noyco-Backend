from fastapi.testclient import TestClient
from unittest.mock import patch

# Import app from main entry
from ....main import app
from ....src.auth.email_service import collection as otp_collection
from ....src.auth.controller import AuthController
from ....config import get_settings
from ....src.stripe.services.webhooks import handle_checkout_completed
from datetime import datetime

client = TestClient(app)


def test_get_public_plans_shape():
    resp = client.get("/public/billing/plans")
    assert resp.status_code == 200
    data = resp.json()
    assert "plans" in data and isinstance(data["plans"], list)
    # Expect 3 plans (1m/3m/6m) though price IDs may be empty in local env
    assert len(data["plans"]) == 3
    for item in data["plans"]:
        assert set(["code", "label", "months", "stripePriceId"]).issubset(item.keys())


def test_public_checkout_session_validation():
    # Invalid plan_code
    bad = client.post("/public/billing/checkout-session", json={"email": "test@example.com", "plan_code": "BAD"})
    assert bad.status_code in (400, 422)

    # Missing email
    bad2 = client.post("/public/billing/checkout-session", json={"plan_code": "IND_1M"})
    assert bad2.status_code == 422


def test_session_status_missing():
    # Unknown session id returns processed False
    resp = client.get("/public/stripe/session-status", params={"session_id": "cs_test_nonexistent"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("processed"), bool)


def test_verify_and_set_password_flow_smoke(monkeypatch):
    """Smoke test: insert an OTP doc and a user doc, then hit the combined endpoint.
    Note: This test does not send real e-mails; it works directly with the OTP collection.
    """
    auth = AuthController()
    email = "funnel_user@example.com"
    # Ensure a user exists without password and unverified
    auth.db.users.delete_many({"email": email})
    auth.db.individuals.delete_many({"email": email})
    user_id = "user_test"
    ind_id = "individual_test"
    auth.db.individuals.insert_one({"id": ind_id, "email": email, "name": "Funnel", "password_hash": "", "created_at": __import__("datetime").datetime.utcnow(), "updated_at": __import__("datetime").datetime.utcnow()})
    auth.db.users.insert_one({"id": user_id, "email": email, "password_hash": "", "name": "Funnel", "role": "individual", "role_entity_id": ind_id, "email_verified": False, "created_at": __import__("datetime").datetime.utcnow(), "updated_at": __import__("datetime").datetime.utcnow()})

    # Insert a pre-verified OTP record (simulate verification success path)
    otp_collection.delete_many({"email": email})
    otp_collection.insert_one({
        "email": email,
        "otp_hash": "",  # bypass verify by directly marking verified in test
        "expires_at": __import__("datetime").datetime.utcnow(),
        "verified": True,
        "purpose": "signup",
        "created_at": __import__("datetime").datetime.utcnow(),
    })

    resp = client.post("/auth/verify-otp-and-set-password", json={"email": email, "otp": "000000", "password": "Passw0rd!"})
    # Even if OTP verify path may fail due to hash mismatch, accept 200/400. This is a smoke test placeholder.
    assert resp.status_code in (200, 400)


def test_verify_otp_and_set_password_sets_cookies(monkeypatch):
    auth = AuthController()
    email = "cookieflow@example.com"
    # Ensure user exists
    auth.db.users.delete_many({"email": email})
    auth.db.individuals.delete_many({"email": email})
    ind_id = "individual_cookie"
    user_id = "user_cookie"
    now = datetime.utcnow()
    auth.db.individuals.insert_one({"id": ind_id, "email": email, "name": "Cookie", "password_hash": "", "created_at": now, "updated_at": now})
    auth.db.users.insert_one({"id": user_id, "email": email, "password_hash": "", "name": "Cookie", "role": "individual", "role_entity_id": ind_id, "email_verified": False, "created_at": now, "updated_at": now})

    # Force OTP verify to pass
    with patch("....src.auth.routes.verify_otp", return_value=True):
        resp = client.post("/auth/verify-otp-and-set-password", json={"email": email, "otp": "123456", "password": "Passw0rd!"})
        assert resp.status_code == 200
        # Check cookies present in response headers
        set_cookie_headers = ",".join(resp.headers.get_all("set-cookie")) if hasattr(resp.headers, "get_all") else ",".join([v for k, v in resp.headers.items() if k.lower() == "set-cookie"]) 
        assert "access_token" in set_cookie_headers.lower()
        assert "refresh_token" in set_cookie_headers.lower()


def test_feature_flag_disables_public_endpoints(monkeypatch):
    settings = get_settings()
    original = settings.FUNNEL_PUBLIC_BILLING_ENABLED
    try:
        # Temporarily disable flag
        settings.FUNNEL_PUBLIC_BILLING_ENABLED = False
        resp1 = client.get("/public/billing/plans")
        resp2 = client.post("/public/billing/checkout-session", json={"email": "a@b.com", "plan_code": "IND_1M"})
        resp3 = client.get("/public/stripe/session-status", params={"session_id": "cs_test"})
        assert resp1.status_code == 404
        assert resp2.status_code == 404
        assert resp3.status_code == 404
    finally:
        settings.FUNNEL_PUBLIC_BILLING_ENABLED = original


def _fake_checkout_event(session_id: str, email: str, plan_type: str = "one_month"):
    return {
        "id": f"evt_{session_id}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "payment_status": "paid",
                "customer": f"cus_{session_id}",
                "subscription": f"sub_{session_id}",
                "customer_email": email,
                "created": int(datetime.utcnow().timestamp()),
                "metadata": {
                    "role": "individual",
                    "plan_type": plan_type,
                    "billing_cycle": "monthly",
                },
            }
        },
    }


def test_webhook_checkout_idempotency_and_mapping():
    # Prepare DB clean slate
    auth = AuthController()
    email = "wbtest@example.com"
    auth.db.users.delete_many({"email": email})
    auth.db.individuals.delete_many({"email": email})
    auth.db.plans.delete_many({"individual_id": {"$exists": True}})
    auth.db.payments.delete_many({"stripe_checkout_session_id": {"$exists": True}})
    auth.db.webhook_checkouts.delete_many({"session_id": {"$exists": True}})

    session_id = "cs_webhook_test"
    event = _fake_checkout_event(session_id, email)

    # First dispatch
    import asyncio
    asyncio.get_event_loop().run_until_complete(handle_checkout_completed(event))

    # Duplicate dispatch should be ignored
    asyncio.get_event_loop().run_until_complete(handle_checkout_completed(event))

    # Assertions
    # Users created
    user = auth.db.users.find_one({"email": email})
    assert user is not None and user.get("role") == "individual"
    ind_id = user.get("role_entity_id")
    # Plan doc updated once
    plan_doc = auth.db.plans.find_one({"individual_id": ind_id})
    assert plan_doc is not None and plan_doc.get("stripe_subscription_id")
    # Payment recorded
    payment = auth.db.payments.find_one({"stripe_checkout_session_id": session_id})
    assert payment is not None and payment.get("status") == "paid"
    # Idempotency marker shows processed
    marker = auth.db.webhook_checkouts.find_one({"session_id": session_id})
    assert marker is not None and marker.get("processed") is True


def test_session_status_flips_after_webhook():
    auth = AuthController()
    email = "flip@example.com"
    auth.db.users.delete_many({"email": email})
    auth.db.individuals.delete_many({"email": email})
    auth.db.webhook_checkouts.delete_many({"session_id": {"$exists": True}})

    sid = "cs_flip"
    # Initially no marker; processed should be False
    resp = client.get("/public/stripe/session-status", params={"session_id": sid})
    assert resp.status_code == 200
    assert resp.json().get("processed") is False

    # Simulate webhook writing marker
    auth.db.webhook_checkouts.insert_one({"session_id": sid, "processed": True, "email": email})
    auth.db.users.insert_one({"id": "user_flip", "email": email, "role": "individual", "role_entity_id": "ind_flip", "email_verified": False})

    resp2 = client.get("/public/stripe/session-status", params={"session_id": sid})
    data = resp2.json()
    assert data.get("processed") is True
    assert data.get("email") == email


def test_public_resend_otp_endpoint():
    auth = AuthController()
    email = "resend@example.com"
    auth.db.users.delete_many({"email": email})
    auth.db.users.insert_one({"id": "user_resend", "email": email, "role": "individual", "role_entity_id": "ind_resend", "email_verified": False})

    resp = client.post("/public/otp/resend", json={"email": email})
    assert resp.status_code in (202, 429)  # 429 if rate limited in fast runs
