from datetime import datetime
import stripe
from typing import Optional, Dict, Any

from ..client import get_stripe
from ..config import get_settings
from ..audit import log
from ..idempotency import mark_processed
from ...billing.schema import UserRole, PlanType, PlanStatus
from ...billing.controller import BillingController
from ...auth.controller import AuthController
from ...auth.email_service import send_signup_otp


# Stripe client and settings (tests may monkeypatch these module attributes)
stripe = get_stripe()
settings = get_settings()

# Expose a controller instance and helper for tests to patch
controller = BillingController()


def _controller() -> BillingController:
    return controller


def _auth() -> AuthController:
    return AuthController()


async def handle_checkout_completed(event: Dict[str, Any]):
    """Legacy Checkout Session completion handler.

    Creates/updates a Subscription Schedule for intro -> recurring phases,
    activates plan for individuals, and persists Stripe IDs onto the plan doc.
    """
    session = event["data"]["object"]
    metadata = session.get("metadata", {})
    role = metadata.get("role")
    role_entity_id = metadata.get("role_entity_id")
    plan = metadata.get("plan_type")
    subscription_id = session.get("subscription")
    customer_id = session.get("customer")

    try:
        # Only individual plans are supported in this release
        if role == UserRole.INDIVIDUAL.value and subscription_id:
            # Map plan -> price IDs (intro vs recurring)
            plan_map = {
                "one_month": {
                    "intro": settings.IND_1M_INTRO_MONTHLY,
                    "intro_iterations": 1,
                    "recurring": settings.IND_1M_RECUR_MONTHLY,
                    "interval": "1mo",
                },
                "three_months": {
                    "intro": settings.IND_3M_INTRO_QUARTERLY,
                    "intro_iterations": 1,
                    "recurring": settings.IND_3M_RECUR_MONTHLY,
                    "interval": "1mo",
                },
                "six_months": {
                    "intro": settings.IND_6M_INTRO_SEMIANNUAL,
                    "intro_iterations": 1,
                    "recurring": settings.IND_6M_RECUR_MONTHLY,
                    "interval": "1mo",
                },
            }
            mapped = plan_map.get((plan or "").lower())
            schedule_id: Optional[str] = None
            if mapped and mapped.get("intro") and mapped.get("recurring"):
                # Create or attach schedule to subscription
                sub = stripe.Subscription.retrieve(subscription_id)
                existing_schedule = sub.get("schedule")
                if existing_schedule:
                    schedule_id = existing_schedule if isinstance(existing_schedule, str) else existing_schedule.get("id")
                else:
                    sched = stripe.SubscriptionSchedule.create(from_subscription=subscription_id)
                    schedule_id = sched.get("id")

                # compute intro phase and subsequent recurring phase
                schedule_obj = stripe.SubscriptionSchedule.retrieve(schedule_id)
                current_phase = schedule_obj.get("current_phase") or {}
                current_start = current_phase.get("start_date")
                intro_phase = {
                    "items": [{"price": mapped["intro"]}],
                    "iterations": mapped.get("intro_iterations", 1),
                }
                if current_start:
                    intro_phase["start_date"] = current_start
                else:
                    from time import time as _now
                    intro_phase["start_date"] = int(_now())
                recurring_phase = {"items": [{"price": mapped["recurring"]}]}

                stripe.SubscriptionSchedule.modify(
                    schedule_id,
                    phases=[intro_phase, recurring_phase],
                    metadata={
                        "role": role,
                        "role_entity_id": role_entity_id,
                        "plan_type": plan,
                    },
                )
                log(
                    "subscription_schedule_update",
                    {
                        "plan_type": plan,
                        "role": role,
                        "role_entity_id": role_entity_id,
                        "intro_price_id": mapped["intro"],
                        "recurring_price_id": mapped["recurring"],
                        "subscription_id": subscription_id,
                        "schedule_id": schedule_id,
                    },
                    "ok",
                    "updated",
                )

                # Activate plan via controller and persist Stripe ids
                try:
                    plan_enum = PlanType(plan) if plan else None
                except Exception:
                    plan_enum = None
                if role_entity_id and plan_enum:
                    try:
                        await _controller().select_individual_plan(
                            individual_id=role_entity_id,
                            plan_type=plan_enum,
                            user_id="stripe-webhook",
                        )
                    except Exception as e:
                        # Non-fatal if already selected
                        log("select_plan_on_checkout", metadata, "error", str(e))

                _controller().db.plans.update_one(
                    {"individual_id": role_entity_id},
                    {"$set": {
                        "status": PlanStatus.ACTIVE.value,
                        "stripe_customer_id": customer_id,
                        "stripe_subscription_id": subscription_id,
                        "stripe_schedule_id": schedule_id,
                        "intro_price_id": mapped["intro"],
                        "recurring_price_id": mapped["recurring"],
                        "recurring_interval": mapped["interval"],
                        "last_event_id": event.get("id"),
                        "updated_at": datetime.utcnow(),
                    }},
                    upsert=False,
                )
        log("checkout_completed", metadata, "ok")
    except Exception as e:
        log("checkout_completed", metadata if isinstance(metadata, dict) else {}, "error", str(e))
        raise


async def handle_invoice_payment_failed(event: Dict[str, Any]):
    invoice = event["data"]["object"]
    metadata = invoice.get("metadata", {})
    role = metadata.get("role")
    role_entity_id = metadata.get("role_entity_id")
    try:
        if role == UserRole.INDIVIDUAL.value:
            _controller().db.plans.update_one(
                {"individual_id": role_entity_id},
                {"$set": {
                    "status": PlanStatus.PAST_DUE.value,
                    "last_event_id": event.get("id"),
                    "updated_at": datetime.utcnow(),
                    "stripe_subscription_id": invoice.get("subscription"),
                    "stripe_customer_id": invoice.get("customer"),
                }},
            )
        log("invoice_payment_failed", metadata, "ok")
    except Exception as e:
        log("invoice_payment_failed", metadata, "error", str(e))
        raise


async def handle_invoice_payment_succeeded(event: Dict[str, Any]):
    """Primary fulfillment handler for Payment Element flow.

    - Ensures plan activation and intro->recurring schedule on first invoice
    - Upserts payment record with robust fallbacks
    - Provisions public Individual + OTP if needed
    """
    invoice = event["data"]["object"]
    metadata = invoice.get("metadata", {})
    role = metadata.get("role")
    role_entity_id = metadata.get("role_entity_id")
    plan = metadata.get("plan_type")
    customer_id = invoice.get("customer")
    subscription_id = invoice.get("subscription")
    billing_reason = invoice.get("billing_reason")

    try:
        # Backfill role/plan from subscription metadata if missing
        if not (role and role_entity_id and plan) and subscription_id:
            try:
                sub = stripe.Subscription.retrieve(subscription_id)
                sub_meta = sub.get("metadata") or {}
                role = role or sub_meta.get("role")
                role_entity_id = role_entity_id or sub_meta.get("role_entity_id")
                plan = plan or sub_meta.get("plan_type")
            except Exception:
                pass

        # Individual plan activation + optional provisional user upsert
        if role == UserRole.INDIVIDUAL.value:
            # If role_entity_id is missing (public flow), derive from customer e-mail and create
            if not role_entity_id:
                try:
                    buyer_email = None
                    try:
                        cust = stripe.Customer.retrieve(customer_id) if customer_id else None
                        buyer_email = (cust.get("email") if isinstance(cust, dict) else None)
                    except Exception:
                        buyer_email = None
                    if buyer_email:
                        auth = _auth()
                        user_doc = auth.db.users.find_one({"email": buyer_email})
                        if not user_doc:
                            created_at = datetime.utcnow()
                            import uuid as _uuid
                            individual_id = f"individual_{_uuid.uuid4().hex[:12]}"
                            auth.db.individuals.insert_one({
                                "id": individual_id,
                                "name": buyer_email.split("@")[0],
                                "email": buyer_email,
                                "password_hash": "",
                                "phone": "Not provided",
                                "created_at": created_at,
                                "updated_at": created_at,
                                "onboarding_completed": False,
                            })
                            user_id = f"user_{_uuid.uuid4().hex[:12]}"
                            auth.db.users.insert_one({
                                "id": user_id,
                                "email": buyer_email,
                                "password_hash": "",
                                "name": buyer_email.split("@")[0],
                                "role": UserRole.INDIVIDUAL.value,
                                "role_entity_id": individual_id,
                                "department": None,
                                "is_active": True,
                                "email_verified": False,
                                "created_at": created_at,
                                "updated_at": created_at,
                                "last_login": None,
                            })
                            role_entity_id = individual_id
                            try:
                                send_signup_otp(buyer_email, buyer_email.split("@")[0])
                            except Exception as e:
                                log("otp_send", {"email": buyer_email, "invoice_id": invoice.get("id")}, "error", str(e))
                        else:
                            role_entity_id = user_doc.get("role_entity_id")
                            email_verified = bool(user_doc.get("email_verified", False))
                            has_password = bool(user_doc.get("password_hash", "").strip())
                            if (not email_verified) or (not has_password):
                                try:
                                    send_signup_otp(buyer_email, user_doc.get("name"))
                                except Exception as e:
                                    log("otp_send", {"email": buyer_email, "invoice_id": invoice.get("id")}, "error", str(e))
                except Exception as e:
                    log("public_user_upsert", metadata, "error", str(e))

            # Activate plan via controller (first purchase)
            try:
                plan_enum = PlanType(plan) if plan else None
            except Exception:
                plan_enum = None
            if role_entity_id and plan_enum:
                try:
                    await _controller().select_individual_plan(
                        individual_id=role_entity_id,
                        plan_type=plan_enum,
                        user_id="stripe-webhook",
                    )
                except Exception as e:
                    log("select_plan_on_invoice", metadata, "error", str(e))

            _controller().db.plans.update_one(
                {"individual_id": role_entity_id},
                {"$set": {"status": PlanStatus.ACTIVE.value, "last_event_id": event.get("id"), "updated_at": datetime.utcnow()}},
            )
            log("plan_status_transition", {
                "role": role,
                "role_entity_id": role_entity_id,
                "new_status": PlanStatus.ACTIVE.value,
                "stripe_customer_id": invoice.get("customer"),
                "stripe_subscription_id": invoice.get("subscription"),
                "event_id": event.get("id"),
            }, "ok")

        # Persist payment record in payments collection (best-effort)
        try:
            payment_intent_id = invoice.get("payment_intent")
            charge_id = None
            charge = None
            amount = invoice.get("amount_due") or invoice.get("amount_paid") or 0
            currency = invoice.get("currency")
            amount_received = invoice.get("amount_paid") or 0

            if payment_intent_id:
                try:
                    pi = stripe.PaymentIntent.retrieve(payment_intent_id, expand=["charges.data.balance_transaction"])
                    if getattr(pi, "charges", None) and pi.charges.data:
                        charge = pi.charges.data[0]
                        charge_id = charge.id
                        amount = getattr(charge, "amount", None) or amount
                        currency = getattr(charge, "currency", None) or currency
                except Exception:
                    pass

            net_amount = None
            fee_amount = None
            if charge and getattr(charge, "balance_transaction", None):
                try:
                    bal_txn = charge.balance_transaction if isinstance(charge.balance_transaction, dict) else stripe.BalanceTransaction.retrieve(charge.balance_transaction)
                    net_amount = bal_txn.get("net")
                    fee_amount = bal_txn.get("fee")
                except Exception:
                    pass

            # Derive plan_name and tax from invoice lines
            lines = (invoice.get("lines", {}) or {}).get("data", [])
            first_line = lines[0] if lines else {}
            plan_name = None
            try:
                plan_name = (first_line.get("plan", {}) or {}).get("nickname") or (first_line.get("price", {}) or {}).get("nickname")
            except Exception:
                plan_name = None
            tax_amount = invoice.get("tax")

            payments_col = _controller().db["payments"]
            try:
                payments_col.create_index("stripe_invoice_id", unique=True)
            except Exception:
                pass

            # Fallbacks
            plan_type_value = metadata.get("plan_type") or plan
            if net_amount is None and fee_amount is not None and amount_received is not None:
                try:
                    net_amount = int(amount_received) - int(fee_amount)
                except Exception:
                    pass

            payments_col.update_one(
                {"stripe_invoice_id": invoice.get("id")},
                {"$set": {
                    "stripe_invoice_id": invoice.get("id"),
                    "stripe_payment_intent_id": payment_intent_id,
                    "stripe_charge_id": charge_id,
                    "stripe_customer_id": invoice.get("customer"),
                    "stripe_subscription_id": invoice.get("subscription"),
                    "user_id": metadata.get("user_id"),
                    "role": role,
                    "role_entity_id": role_entity_id,
                    "plan_type": plan_type_value,
                    "cycle": metadata.get("billing_cycle", "monthly"),
                    "amount": amount,
                    "currency": currency,
                    "amount_received": amount_received,
                    "net_amount": net_amount,
                    "fee_amount": fee_amount,
                    "status": invoice.get("status"),
                    "payment_status": invoice.get("status"),
                    "refunded": False,
                    "refund_amount": 0,
                    "dispute_status": None,
                    "metadata": {"plan_name": plan_name, "tax_amount": tax_amount},
                    "paid_at": datetime.utcnow(),
                    "stripe_created": datetime.fromtimestamp(invoice.get("created")) if invoice.get("created") else None,
                    "payment_source": "invoice_payment_succeeded",
                    "webhook_event_type": event.get("type"),
                    "webhook_event_id": event.get("id"),
                }},
                upsert=True,
            )
        except Exception as db_err:
            log("payment_record", metadata, "error", str(db_err))

        # On first invoice, attach schedule and persist ids
        try:
            if role == UserRole.INDIVIDUAL.value and billing_reason == "subscription_create" and subscription_id:
                plan_map = {
                    "one_month": {
                        "intro": settings.IND_1M_INTRO_MONTHLY,
                        "intro_iterations": 1,
                        "recurring": settings.IND_1M_RECUR_MONTHLY,
                        "interval": "1mo",
                    },
                    "three_months": {
                        "intro": settings.IND_3M_INTRO_QUARTERLY,
                        "intro_iterations": 1,
                        "recurring": settings.IND_3M_RECUR_MONTHLY,
                        "interval": "1mo",
                    },
                    "six_months": {
                        "intro": settings.IND_6M_INTRO_SEMIANNUAL,
                        "intro_iterations": 1,
                        "recurring": settings.IND_6M_RECUR_MONTHLY,
                        "interval": "1mo",
                    },
                }
                mapped = plan_map.get((plan or "").lower())
                schedule_id = None
                if mapped and mapped["intro"] and mapped["recurring"]:
                    try:
                        sub = stripe.Subscription.retrieve(subscription_id)
                        existing_schedule = sub.get("schedule")
                        if existing_schedule:
                            schedule_id = existing_schedule if isinstance(existing_schedule, str) else existing_schedule.get("id")
                        else:
                            sched = stripe.SubscriptionSchedule.create(from_subscription=subscription_id)
                            schedule_id = sched.get("id")

                        schedule_obj = stripe.SubscriptionSchedule.retrieve(schedule_id)
                        current_phase = schedule_obj.get("current_phase") or {}
                        current_start = current_phase.get("start_date")

                        intro_phase = {
                            "items": [{"price": mapped["intro"]}],
                            "iterations": mapped.get("intro_iterations", 1),
                        }
                        if current_start:
                            intro_phase["start_date"] = current_start
                        else:
                            from time import time as _now
                            intro_phase["start_date"] = int(_now())

                        recurring_phase = {"items": [{"price": mapped["recurring"]}]}

                        stripe.SubscriptionSchedule.modify(
                            schedule_id,
                            phases=[intro_phase, recurring_phase],
                            metadata={"role": role, "role_entity_id": role_entity_id, "plan_type": plan},
                        )
                        log(
                            "subscription_schedule_update",
                            {
                                "plan_type": plan,
                                "role": role,
                                "role_entity_id": role_entity_id,
                                "intro_price_id": mapped["intro"],
                                "recurring_price_id": mapped["recurring"],
                                "subscription_id": subscription_id,
                                "schedule_id": schedule_id,
                            },
                            "ok",
                            "updated",
                        )
                    except Exception as sched_err:
                        log("subscription_schedule_update", metadata, "error", str(sched_err))

                    try:
                        _controller().db.plans.update_one(
                            {"individual_id": role_entity_id},
                            {"$set": {
                                "stripe_customer_id": customer_id,
                                "stripe_subscription_id": subscription_id,
                                "stripe_schedule_id": schedule_id,
                                "intro_price_id": mapped["intro"],
                                "recurring_price_id": mapped["recurring"],
                                "recurring_interval": mapped["interval"],
                                "last_event_id": event.get("id"),
                                "updated_at": datetime.utcnow(),
                            }},
                            upsert=False,
                        )
                    except Exception:
                        pass
        except Exception as e:
            log("schedule_on_first_invoice", metadata, "error", str(e))

        log("invoice_payment_succeeded", metadata, "ok")
    except Exception as e:
        log("invoice_payment_succeeded", metadata, "error", str(e))
        raise


async def handle_subscription_updated(event: Dict[str, Any]):
    subscription = event["data"]["object"]
    metadata = subscription.get("metadata", {})
    role = metadata.get("role")
    role_entity_id = metadata.get("role_entity_id")

    status = subscription.get("status")
    try:
        if status == "active":
            new_status = PlanStatus.ACTIVE
        elif status == "past_due":
            new_status = PlanStatus.PAST_DUE
        elif status in ["unpaid", "paused"]:
            new_status = PlanStatus.SUSPENDED
        elif status == "canceled":
            new_status = PlanStatus.CANCELLED
        else:
            new_status = PlanStatus.ACTIVE

        if role == UserRole.INDIVIDUAL.value:
            update_doc = {
                "status": new_status.value,
                "last_event_id": event.get("id"),
                "updated_at": datetime.utcnow(),
                "cancel_at_period_end": subscription.get("cancel_at_period_end"),
                "current_period_end": subscription.get("current_period_end"),
                "stripe_subscription_status": subscription.get("status"),
            }
            if subscription.get("cancel_at"):
                update_doc["cancel_at"] = subscription.get("cancel_at")
            _controller().db.plans.update_one(
                {"individual_id": role_entity_id},
                {"$set": update_doc},
            )
        log("plan_status_transition", {
            "role": role,
            "role_entity_id": role_entity_id,
            "new_status": new_status.value,
            "stripe_subscription_id": subscription.get("id"),
            "event_id": event.get("id"),
        }, "ok")
        log("subscription_updated", metadata, "ok")
    except Exception as e:
        log("subscription_updated", metadata, "error", str(e))
        raise


async def handle_subscription_deleted(event: Dict[str, Any]):
    subscription = event["data"]["object"]
    metadata = subscription.get("metadata", {})
    role = metadata.get("role")
    role_entity_id = metadata.get("role_entity_id")

    try:
        if role == UserRole.INDIVIDUAL.value:
            _controller().db.plans.update_one(
                {"individual_id": role_entity_id},
                {"$set": {
                    "status": PlanStatus.CANCELLED.value,
                    "last_event_id": event.get("id"),
                    "updated_at": datetime.utcnow(),
                    "cancel_at_period_end": False,
                    "current_period_end": subscription.get("current_period_end"),
                    "stripe_subscription_status": subscription.get("status"),
                }},
            )
        log("plan_status_transition", {
            "role": role,
            "role_entity_id": role_entity_id,
            "new_status": PlanStatus.CANCELLED.value,
            "stripe_subscription_id": subscription.get("id"),
            "event_id": event.get("id"),
        }, "ok")
        log("subscription_deleted", metadata, "ok")
    except Exception as e:
        log("subscription_deleted", metadata, "error", str(e))
        raise


# Dispatch map must be defined after handler functions
dispatch_map = {
    "checkout.session.completed": handle_checkout_completed,
    "invoice.payment_failed": handle_invoice_payment_failed,
    "invoice.payment_succeeded": handle_invoice_payment_succeeded,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
}


async def dispatch(event: Dict[str, Any]):
    try:
        log("webhook_received", {"type": event.get("type"), "event_id": event.get("id")}, "ok")
    except Exception:
        pass

    try:
        eid = event.get("id")
        ledger = _controller().db["stripe_events_processed"]
        try:
            ledger.create_index("event_id", unique=True)
        except Exception:
            pass
        res = ledger.update_one(
            {"event_id": eid},
            {"$setOnInsert": {"event_id": eid, "created_at": datetime.utcnow()}},
            upsert=True,
        )
        if getattr(res, "upserted_id", None) is None:
            try:
                ledger.update_one({"event_id": eid}, {"$inc": {"replay_count": 1}, "$set": {"last_seen_at": datetime.utcnow()}})
            except Exception:
                pass
            log("webhook_idempotent_skip", {"event_id": eid, "type": event.get("type")}, "ok")
            return
    except Exception as idemp_err:
        log("webhook_idempotency", {"type": event.get("type")}, "error", str(idemp_err))

    etype = event["type"]
    handler = dispatch_map.get(etype)
    if handler:
        await handler(event)
        try:
            mark_processed(event.get("id"))
        except Exception:
            pass
