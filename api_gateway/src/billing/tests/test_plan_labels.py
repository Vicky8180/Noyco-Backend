import types
import sys
import os

# Pre-stub the database module used by controller to avoid real DB access during import
fake_db_mod = types.ModuleType("api_gateway.database.db")

class _DummyDB:
    def __getattr__(self, name):
        class _C:
            def create_index(self, *a, **k):
                return None
        return _C()

def get_database():
    return _DummyDB()

fake_db_mod.get_database = get_database  # type: ignore[attr-defined]
sys.modules["api_gateway.database.db"] = fake_db_mod

from api_gateway.src.billing.controller import PLAN_DETAILS_INDIVIDUAL
from api_gateway.src.billing.schema import PlanType


def test_all_plans_monthly_recurring_label_and_amount():
    for plan in (PlanType.ONE_MONTH, PlanType.THREE_MONTHS, PlanType.SIX_MONTHS):
        details = PLAN_DETAILS_INDIVIDUAL[plan]
        assert details["recurring_interval_label"] == "every 1 month"
        assert float(details["recurring_price"]) == 29.99


def test_intro_prices_updated():
    assert float(PLAN_DETAILS_INDIVIDUAL[PlanType.ONE_MONTH]["intro_price"]) == 19.99
    assert float(PLAN_DETAILS_INDIVIDUAL[PlanType.THREE_MONTHS]["intro_price"]) == 49.99
    assert float(PLAN_DETAILS_INDIVIDUAL[PlanType.SIX_MONTHS]["intro_price"]) == 79.99
