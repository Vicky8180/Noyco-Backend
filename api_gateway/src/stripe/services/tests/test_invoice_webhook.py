import asyncio
import pytest


class FakeStripe:
    class PaymentIntent:
        @staticmethod
        def retrieve(pi_id, expand=None):
            class Charges:
                data = []
            return type("PI", (), {"id": pi_id, "charges": Charges(), "status": "succeeded"})

    class BalanceTransaction:
        @staticmethod
        def retrieve(_):
            return {"net": 1000, "fee": 100}

    class Subscription:
        store = {
            "sub_sched_1": {"id": "sub_sched_1", "schedule": None, "latest_invoice": {"id": "in_1"}},
        }

        @classmethod
        def retrieve(cls, sub_id, expand=None):
            return cls.store.get(sub_id, {"id": sub_id, "schedule": None, "latest_invoice": {"id": "in_x"}})

    class SubscriptionSchedule:
        schedules = {}

        @classmethod
        def create(cls, from_subscription):
            sid = f"ss_{from_subscription}"
            cls.schedules[sid] = {"id": sid, "phases": [], "current_phase": {}}
            return {"id": sid}

        @classmethod
        def retrieve(cls, schedule_id):
            return cls.schedules.get(schedule_id, {"id": schedule_id, "phases": [], "current_phase": {}})

        @classmethod
        def modify(cls, schedule_id, phases=None, metadata=None):
            obj = cls.schedules.setdefault(schedule_id, {"id": schedule_id})
            obj["phases"] = phases or []
            obj["metadata"] = metadata or {}
            return obj


@pytest.fixture(autouse=True)
def patch_stripe(monkeypatch):
    from .. import webhooks
    fake = FakeStripe()
    monkeypatch.setattr(webhooks, "stripe", fake)
    yield


@pytest.mark.asyncio
async def test_invoice_payment_succeeded_creates_schedule_and_persists_ids(monkeypatch):
    from .. import webhooks

    # Patch controller DB with a fake in-memory structure
    class FakePlans:
        def __init__(self):
            self.docs = {}
        def update_one(self, filt, update, upsert=False):
            key = filt.get("individual_id")
            doc = self.docs.setdefault(key, {"individual_id": key})
            doc.update(update.get("$set", {}))
    class FakeDB:
        def __init__(self):
            self.plans = FakePlans()
            self["payments"] = types.SimpleNamespace(create_index=lambda *a, **k: None, update_one=lambda *a, **k: None)
        def __getitem__(self, name):
            return self.__dict__[name]

    import types
    fdb = FakeDB()
    class FakeController:
        def __init__(self):
            self.db = fdb
        async def select_individual_plan(self, individual_id, plan_type, user_id):
            fdb.plans.update_one({"individual_id": individual_id}, {"$set": {"plan_type": plan_type.value}})

    monkeypatch.setattr(webhooks, "_controller", lambda: FakeController())

    event = {
        "id": "evt_1",
        "type": "invoice.payment_succeeded",
        "data": {"object": {
            "id": "in_1",
            "customer": "cus_1",
            "subscription": "sub_sched_1",
            "billing_reason": "subscription_create",
            "metadata": {
                "role": "individual",
                "role_entity_id": "individual_123",
                "plan_type": "one_month",
            },
        }}
    }

    await webhooks.handle_invoice_payment_succeeded(event)

    # Verify schedule created and plan doc updated with ids
    doc = fdb.plans.docs.get("individual_123")
    assert doc is not None
    assert doc.get("stripe_subscription_id") == "sub_sched_1"
    assert doc.get("stripe_schedule_id") == f"ss_{'sub_sched_1'}"
