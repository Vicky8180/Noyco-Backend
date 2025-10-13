import types
import pytest

from .. import sessions as sess
from ....billing.schema import UserRole


class FakeUser:
    def __init__(self, email, role_entity_id="ind_test"):
        self.email = email
        self.role = UserRole.INDIVIDUAL
        self.role_entity_id = role_entity_id
        self.user_id = "user_test"


def test_sessions_uses_quarterly_and_semiannual_intro_when_present(monkeypatch):
    # Patch settings to include quarterly/semiannual price IDs
    class S:
        IND_1M_INTRO_MONTHLY = "price_intro_1m"
        IND_3M_INTRO_QUARTERLY = "price_intro_3m_q"
        IND_3M_INTRO_MONTHLY = "price_intro_3m_legacy"
        IND_6M_INTRO_SEMIANNUAL = "price_intro_6m_sa"
        IND_6M_INTRO_MONTHLY = "price_intro_6m_legacy"
        SUCCESS_URL = "http://localhost/success"
        CANCEL_URL = "http://localhost/cancel"
    monkeypatch.setattr(sess, "settings", S())

    captured = {"price": None}

    class FakeCheckout:
        class Session:
            @staticmethod
            def create(**kwargs):
                items = kwargs.get("line_items", [])
                captured["price"] = items[0]["price"] if items else None
                return types.SimpleNamespace(id="cs_test", url="https://example.com")

    class FakeStripe:
        checkout = FakeCheckout

    monkeypatch.setattr(sess, "stripe", FakeStripe)

    # Three months plan should use quarterly price
    user = FakeUser("x@y.z")
    sess.create_checkout_session(user=user, plan_type="three_months")
    assert captured["price"] == "price_intro_3m_q"

    # Six months plan should use semiannual price
    sess.create_checkout_session(user=user, plan_type="six_months")
    assert captured["price"] == "price_intro_6m_sa"
