import os
import sys
import types
import pytest

# Ensure minimal env for StripeSettings before importing module under test
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_dummy")
os.environ.setdefault("STRIPE_PUBLISHABLE_KEY", "pk_test_dummy")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_dummy")

# Stub out the Mongo get_database used deep in BillingController to avoid requiring a real DB/config
fake_db_mod = types.ModuleType("api_gateway.database.db")

class _DummyPlansCol:
    def create_index(self, *a, **k):
        return None
    def update_one(self, *a, **k):
        return None

class _DummyCollection:
    def create_index(self, *a, **k):
        return None
    def update_one(self, *a, **k):
        return None

class _DummyDB:
    def __init__(self):
        self.plans = _DummyPlansCol()
    def __getitem__(self, name):
        return _DummyCollection()

def get_database():
    return _DummyDB()

fake_db_mod.get_database = get_database  # type: ignore[attr-defined]
sys.modules["api_gateway.database.db"] = fake_db_mod

# Now it is safe to import the webhook handler and monkeypatch the Stripe client + settings
from api_gateway.src.stripe.services import webhooks as wh
from api_gateway.src.stripe.services.sessions import create_checkout_session
from api_gateway.src.stripe.routes import create_checkout as checkout_route
from fastapi import Request
import asyncio

class DummyStripe:
    class Subscription:
        @staticmethod
        def retrieve(sub_id):
            # No existing schedule
            return {"id": sub_id, "schedule": None}

    class SubscriptionSchedule:
        created = []
        modified = []

        @staticmethod
        def create(**kwargs):
            DummyStripe.SubscriptionSchedule.created.append(kwargs)
            return {"id": "sub_sched_test_123"}

        @staticmethod
        def modify(schedule_id, **kwargs):
            DummyStripe.SubscriptionSchedule.modified.append({"id": schedule_id, **kwargs})
    class checkout:
        class Session:
            @staticmethod
            def create(**kwargs):
                # mimic shape session with id,url
                return types.SimpleNamespace(id="cs_test_123", url="https://checkout.test/s/cs_test_123")

@pytest.fixture(autouse=True)
def patch_stripe(monkeypatch):
    monkeypatch.setattr(wh, "stripe", DummyStripe)

@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    # Provide controlled test settings
    class S:
        IND_1M_INTRO_MONTHLY = "price_intro_1m"
        IND_3M_INTRO_MONTHLY = "price_intro_3m"
        IND_6M_INTRO_MONTHLY = "price_intro_6m"
        # Simulate presence of per-period upfront IDs (should force iterations=1)
        IND_3M_INTRO_QUARTERLY = "price_intro_3m_q"
        IND_6M_INTRO_SEMIANNUAL = "price_intro_6m_sa"
        IND_1M_RECUR_MONTHLY = "price_recur_1m"
        IND_3M_RECUR_MONTHLY = "price_recur_3m"
        IND_6M_RECUR_MONTHLY = "price_recur_6m"
        SUCCESS_URL = "http://localhost/success"
        CANCEL_URL = "http://localhost/cancel"
    monkeypatch.setattr(wh, "settings", S())


def make_event(plan: str):
    # Build a minimal checkout.session.completed event payload
    return {
        "type": "checkout.session.completed",
        "id": "evt_test_123",
        "data": {
            "object": {
                "id": "cs_test_123",
                "payment_status": "paid",
                "customer": "cus_test_123",
                "subscription": "sub_test_123",
                "metadata": {
                    "role": "individual",
                    "role_entity_id": "ind_123",
                    "plan_type": plan,
                },
                "created": 1700000000,
                "amount_total": 1999,
                "currency": "usd",
            }
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plan, intro, recur, iterations",
    [
        ("one_month", "price_intro_1m", "price_recur_1m", 1),
        # When quarterly/semiannual IDs are present in settings, expect 1 iteration and the per-period intro IDs
        ("three_months", "price_intro_3m_q", "price_recur_3m", 1),
        ("six_months", "price_intro_6m_sa", "price_recur_6m", 1),
    ],
)
async def test_schedule_mapping_monthly(monkeypatch, plan, intro, recur, iterations):
    # Patch database writes to no-op
    class DummyDB:
        def __init__(self):
            self.plans = types.SimpleNamespace(update_one=lambda *a, **k: None, create_index=lambda *a, **k: None)
            self.__getitem__ = lambda self, name: types.SimpleNamespace(
                create_index=lambda *a, **k: None,
                update_one=lambda *a, **k: None,
            )
    monkeypatch.setattr(wh.controller, "db", DummyDB())

    # Track that controller.select_individual_plan was called (ACTIVE transition)
    calls = {"count": 0}
    async def fake_select_individual_plan(**kwargs):
        calls["count"] += 1
    monkeypatch.setattr(wh.controller, "select_individual_plan", fake_select_individual_plan)

    event = make_event(plan)
    await wh.handle_checkout_completed(event)

    # Validate schedule was created and then modified with phases
    assert DummyStripe.SubscriptionSchedule.created, "No schedule created"
    assert DummyStripe.SubscriptionSchedule.modified, "No schedule modified to set phases"
    modified = DummyStripe.SubscriptionSchedule.modified[-1]

    phases = modified["phases"]
    assert phases[0]["items"][0]["price"] == intro
    assert phases[1]["items"][0]["price"] == recur
    assert phases[0]["iterations"] == iterations

    # Ensure ACTIVE path invoked through controller
    assert calls["count"] == 1

    # We store interval as label in DB; ensure we mapped to monthly for all
    # (the handler sets recurring_interval label in the DB update)
    # This is validated indirectly via mapping structure; direct check would
    # require intercepting controller.db.plans.update_one arguments.


@pytest.mark.asyncio
async def test_invoice_failed_sets_past_due(monkeypatch):
    # Dummy DB with tracking for update_one calls
    class TrackDB:
        def __init__(self):
            self.updates = []
            self.plans = types.SimpleNamespace(update_one=lambda *a, **k: self.updates.append((a, k)), create_index=lambda *a, **k: None)
            self.__getitem__ = lambda self, name: types.SimpleNamespace(create_index=lambda *a, **k: None, update_one=lambda *a, **k: None)
    tdb = TrackDB()
    monkeypatch.setattr(wh.controller, "db", tdb)

    event = {
        "type": "invoice.payment_failed",
        "id": "evt_failed_1",
        "data": {"object": {"metadata": {"role": "individual", "role_entity_id": "ind_42"}, "customer": "cus_42", "subscription": "sub_42"}}
    }
    await wh.handle_invoice_payment_failed(event)
    # Ensure PAST_DUE written
    assert any(k.get("$set", {}).get("status") == wh.PlanStatus.PAST_DUE.value for _, k in tdb.updates)


@pytest.mark.asyncio
async def test_subscription_updated_status_mapping(monkeypatch):
    class TrackDB:
        def __init__(self):
            self.updates = []
            self.plans = types.SimpleNamespace(update_one=lambda *a, **k: self.updates.append((a, k)), create_index=lambda *a, **k: None)
            self.__getitem__ = lambda self, name: types.SimpleNamespace(create_index=lambda *a, **k: None, update_one=lambda *a, **k: None)
    tdb = TrackDB()
    monkeypatch.setattr(wh.controller, "db", tdb)

    def evt(status):
        return {"type": "customer.subscription.updated", "id": f"evt_{status}", "data": {"object": {"id": "sub_1", "status": status, "metadata": {"role": "individual", "role_entity_id": "ind_99"}}}}

    for st, expected in [
        ("active", wh.PlanStatus.ACTIVE.value),
        ("past_due", wh.PlanStatus.PAST_DUE.value),
        ("unpaid", wh.PlanStatus.SUSPENDED.value),
        ("paused", wh.PlanStatus.SUSPENDED.value),
        ("canceled", wh.PlanStatus.CANCELLED.value),
    ]:
        tdb.updates.clear()
        await wh.handle_subscription_updated(evt(st))
        assert any(k.get("$set", {}).get("status") == expected for _, k in tdb.updates)


@pytest.mark.asyncio
async def test_idempotency_guard_replay(monkeypatch):
    class Ledger:
        def __init__(self):
            self.docs = {}
        def create_index(self, *a, **k):
            return None
        def update_one(self, filter, update, upsert=False):
            key = filter["event_id"]
            if key not in self.docs:
                if upsert:
                    self.docs[key] = {"event_id": key, **update.get("$setOnInsert", {})}
                    class Res: upserted_id = "ok"
                    return Res()
            class Res: upserted_id = None
            return Res()
    class TrackDB:
        def __init__(self):
            self.ledger = Ledger()
        def __getitem__(self, name):
            return self.ledger
    monkeypatch.setattr(wh.controller, "db", TrackDB())

    called = {"count": 0}
    async def dummy_handler(evt):
        called["count"] += 1
    wh.dispatch_map["dummy.event"] = dummy_handler

    evt = {"type": "dummy.event", "id": "evt_same"}
    await wh.dispatch(evt)
    await wh.dispatch(evt)  # replay
    assert called["count"] == 1, "Duplicate event should have been skipped by idempotency guard"


@pytest.mark.asyncio
async def test_checkout_start_sets_pending(monkeypatch):
    # Patch the backend db used in stripe.routes
    from api_gateway.src.stripe import routes as sr
    class TrackPlans:
        def __init__(self):
            self.inserted = []
            self.updated = []
        def find_one(self, q):
            return None
        def update_one(self, *a, **k):
            self.updated.append((a, k))
        def insert_one(self, doc):
            self.inserted.append(doc)
    class TrackDB:
        def __init__(self):
            self.plans = TrackPlans()
    monkeypatch.setattr(sr, "db", TrackDB())

    # Patch session creator to avoid real Stripe call
    async def fake_checkout(*a, **k):
        return {"id": "cs_fake_1", "url": "https://checkout.test/s/cs_fake_1"}
    monkeypatch.setattr(sr, "create_checkout_session", lambda **k: {"id": "cs_fake_1", "url": "https://checkout.test/s/cs_fake_1"})

    class User:
        role = wh.UserRole.INDIVIDUAL
        role_entity_id = "ind_123"
        email = "x@y.z"
        user_id = "u_1"

    # Build a fake request body object
    class Body:
        def __init__(self, plan_type):
            self.plan_type = wh.PlanType.ONE_MONTH

    # Call the route function directly
    resp = await sr.create_checkout(Body(wh.PlanType.ONE_MONTH), types.SimpleNamespace(), User())
    assert resp["checkout_url"].startswith("https://")
    # Ensure PENDING written in plan doc
    assert any(doc.get("status") == wh.PlanStatus.PENDING.value for doc in sr.db.plans.inserted)
