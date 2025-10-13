import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient


class FakeUser:
    def __init__(self):
        self.role = type("Role", (), {"value": "individual"})
        self.role_entity_id = "individual_abc"
        self.email = "user@example.com"


class FakeStripe:
    class Customer:
        @staticmethod
        def create(email: str, metadata=None):
            return {"id": "cus_auth_1", "email": email}

    class Subscription:
        @staticmethod
        def create(**kwargs):
            return {
                "id": "sub_auth_1",
                "latest_invoice": {
                    "id": "in_auth_1",
                    "payment_intent": {"id": "pi_auth_1", "client_secret": "pi_auth_secret_1"}
                }
            }


@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    # Patch stripe client in routes
    from .. import routes as stripe_routes
    monkeypatch.setattr(stripe_routes, "get_stripe", lambda: FakeStripe())
    # Patch DB in routes
    class FakePlans:
        def __init__(self): self.docs = {}
        def find_one(self, q): return None
        def update_one(self, *a, **k): pass
        def insert_one(self, doc): self.docs[doc["individual_id"]] = doc
    class FakeDB:
        def __init__(self): self.plans = FakePlans()
    monkeypatch.setattr(stripe_routes, "db", FakeDB())
    yield


def build_app():
    from ..routes import router
    app = FastAPI()
    # Monkeypatch dependency for JWT auth
    from ..routes import jwt_auth
    jwt_auth.get_current_user = lambda: FakeUser()
    app.include_router(router)
    return app


def test_auth_create_subscription_endpoint():
    app = build_app()
    client = TestClient(app)
    resp = client.post("/stripe/create-subscription", json={"plan_type": "one_month"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["client_secret"].startswith("pi_auth_secret_")
    assert data["subscription_id"].startswith("sub_auth_")
    assert data["customer_id"].startswith("cus_auth_")
