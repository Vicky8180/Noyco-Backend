import types
import pytest
from fastapi.testclient import TestClient


def fake_app():
    # Build a minimal FastAPI app mounting only the public router
    from fastapi import FastAPI
    from ..routes import router as public_router
    app = FastAPI()
    app.include_router(public_router)
    return app


class FakeStripe:
    class Customer:
        @staticmethod
        def list(email: str, limit: int = 1):
            return {"data": []}

        @staticmethod
        def create(email: str, metadata=None):
            return {"id": "cus_test_123", "email": email, "metadata": metadata or {}}

    class Subscription:
        @staticmethod
        def create(**kwargs):
            # Return minimal subscription with latest invoice and PI client secret
            return {
                "id": "sub_test_123",
                "latest_invoice": {
                    "id": "in_test_123",
                    "payment_intent": {
                        "id": "pi_test_123",
                        "client_secret": "pi_test_secret_123",
                    },
                },
            }

    class PaymentIntent:
        @staticmethod
        def retrieve(pi_id):
            return {"id": pi_id, "status": "succeeded", "charges": {"data": []}}

    class SubscriptionRetrieve:
        @staticmethod
        def retrieve(sub_id, expand=None):
            return {"id": sub_id, "status": "active", "latest_invoice": {"paid": True, "customer": {"email": "user@example.com"}}}


@pytest.fixture(autouse=True)
def patch_stripe(monkeypatch):
    from .. import routes as public_routes
    fake = FakeStripe()
    monkeypatch.setattr(public_routes, "get_stripe", lambda: fake)
    yield


def test_public_create_subscription_and_payment_status():
    app = fake_app()
    client = TestClient(app)

    # Create subscription (public)
    resp = client.post("/public/billing/create-subscription", json={"email": "user@example.com", "plan_code": "IND_1M"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["client_secret"].startswith("pi_test_secret_")
    assert data["subscription_id"].startswith("sub_test_")

    # Payment status by PI
    ps = client.get("/public/stripe/payment-status", params={"payment_intent": "pi_test_123"})
    assert ps.status_code == 200
    assert ps.json()["processed"] is True

    # Payment status by subscription id
    ps2 = client.get("/public/stripe/payment-status", params={"subscription_id": "sub_test_123"})
    assert ps2.status_code == 200
    assert ps2.json()["processed"] is True
