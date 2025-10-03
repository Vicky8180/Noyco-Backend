from datetime import datetime
import logging
from ..audit import log
from ..client import get_stripe
from ..config import get_settings
from ..idempotency import mark_processed
from ...billing.schema import PlanType, UserRole, PlanStatus, PlanSelectionRequest
from ...auth.email_service import send_signup_otp
from ...auth.controller import AuthController
from pymongo.errors import DuplicateKeyError

stripe = get_stripe()
settings = get_settings()
logger = logging.getLogger("stripe.webhooks")

def _controller():
    from ...billing.controller import BillingController  # lazy import
    return BillingController()

def _auth():
    return AuthController()

async def handle_checkout_completed(event):
    session = event["data"]["object"]
    if session.get("payment_status") != "paid":
        return
    metadata = session.get("metadata", {})
    def _norm(v: str | None):
        if not v:
            return v
        # Convert Enum-style strings like "UserRole.HOSPITAL" -> "hospital"
        if "." in v:
            return v.split(".")[-1].lower()
        return v.lower()

    role = _norm(metadata.get("role"))
    role_entity_id = metadata.get("role_entity_id" )
    # Require new key plan_type only
    plan = _norm(metadata.get("plan_type"))
    cycle = _norm(metadata.get("billing_cycle", "monthly"))

    try:
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        session_id = session.get("id")

        # ------------------------------------------------------------------
        # Idempotency: ensure each checkout.session.completed is processed once
        # ------------------------------------------------------------------
        db = _controller().db
        try:
            db.webhook_checkouts.create_index("session_id", unique=True)
        except Exception:
            pass
        # Determine buyer email early for marker enrichment
        buyer_email = None
        try:
            details = session.get("customer_details") or {}
            buyer_email = details.get("email") or session.get("customer_email")
        except Exception:
            buyer_email = session.get("customer_email")
        # Upsert marker instead of insert-only to avoid premature duplicate short-circuit
        try:
            db.webhook_checkouts.update_one(
                {"session_id": session_id},
                {
                    "$setOnInsert": {
                        "session_id": session_id,
                        "type": event.get("type"),
                        "inserted_at": datetime.utcnow(),
                        "processed": False,
                    },
                    "$set": {"email": buyer_email},
                },
                upsert=True,
            )
        except Exception:
            pass

        # if role == UserRole.HOSPITAL.value:
        #     # Create a valid PlanSelectionRequest with proper PlanType enum
        #     plan_type = PlanType(plan) if plan else PlanType.LITE
        #     req = PlanSelectionRequest(plan_type=plan_type, id=role_entity_id)
        #     
        #     # Select the plan through controller
        #     await controller.select_plan(request=req, user_id="stripe-webhook")
        #     
        #     # Set default services for hospital plans
        #     default_services = ["privacy", "human_escalation", "checklist"]
        #     
        #     # Persist Stripe IDs in the plans collection
        #     controller.db.plans.update_one(
        #         {"hospital_id": role_entity_id},
        #         {"$set": {
        #             "stripe_customer_id": customer_id, 
        #             "stripe_subscription_id": subscription_id,
        #             "status": PlanStatus.ACTIVE.value,
        #             "selected_services": default_services,
        #             "updated_at": datetime.utcnow()
        #         }},
        #     )
        if role == UserRole.INDIVIDUAL.value:
            # If role_entity_id missing (public funnel), upsert user/individual now
            if not role_entity_id and buyer_email:
                auth = _auth()
                user_doc = auth.db.users.find_one({"email": buyer_email})
                if not user_doc:
                    # Create new individual + user, unverified, no password
                    created_at = datetime.utcnow()
                    import uuid as _uuid
                    individual_id = f"individual_{_uuid.uuid4().hex[:12]}"
                    auth.db.individuals.insert_one({
                        "id": individual_id,
                        "name": buyer_email.split("@")[0],
                        "email": buyer_email,
                        "password_hash": "",  # set later after OTP
                        "phone": "Not provided",
                        "created_at": created_at,
                        "updated_at": created_at,
                        "onboarding_completed": False,
                    })
                    user_id = f"user_{_uuid.uuid4().hex[:12]}"
                    auth.db.users.insert_one({
                        "id": user_id,
                        "email": buyer_email,
                        "password_hash": "",  # set later
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
                    # Send OTP for signup verification
                    try:
                        send_signup_otp(buyer_email, buyer_email.split("@")[0])
                        db.webhook_checkouts.update_one({"session_id": session_id}, {"$set": {"otp_sent": True}})
                    except Exception as e:
                        log("otp_send", {"email": buyer_email, "session_id": session_id}, "error", str(e))
                        # No generic metrics write
                else:
                    # Existing user: determine whether to send OTP
                    role_entity_id = user_doc.get("role_entity_id")
                    email_verified = bool(user_doc.get("email_verified", False))
                    has_password = bool(user_doc.get("password_hash", "").strip())
                    if (not email_verified) or (not has_password):
                        try:
                            send_signup_otp(buyer_email, user_doc.get("name"))
                            db.webhook_checkouts.update_one({"session_id": session_id}, {"$set": {"otp_sent": True}})
                        except Exception as e:
                            log("otp_send", {"email": buyer_email, "session_id": session_id}, "error", str(e))
                            # No generic metrics write
        if role == UserRole.INDIVIDUAL.value:
            # 1) Mark plan ACTIVE on our side
            try:
                plan_enum = PlanType(plan) if plan else None
            except Exception:
                plan_enum = None
            if plan_enum:
                # Use controller to ensure parity with dashboard flow
                await _controller().select_individual_plan(
                    individual_id=role_entity_id,
                    plan_type=plan_enum,
                    user_id="stripe-webhook",
                )

            # 2) Create or attach Subscription Schedule with intro then recurring phases
            # Map plan -> price IDs and recurring interval label
            plan_map = {
                # Intro iterations represent months at the intro price
                # 1 month plan -> 1 month at $19.99, then $29.99/mo
                "one_month": {
                    "intro": settings.IND_1M_INTRO_MONTHLY,
                    "intro_iterations": 1,
                    "recurring": settings.IND_1M_RECUR_MONTHLY,
                    "interval": "1mo",
                },
                # 3 months plan (Option A) -> $49.99 once covering 3 months (price interval_count=3), then $29.99/mo
                "three_months": {
                    "intro": settings.IND_3M_INTRO_MONTHLY,
                    "intro_iterations": 1,
                    "recurring": settings.IND_3M_RECUR_MONTHLY,
                    "interval": "1mo",
                },
                # 6 months plan (Option A) -> $79.99 once covering 6 months (price interval_count=6), then $29.99/mo
                "six_months": {
                    "intro": settings.IND_6M_INTRO_MONTHLY,
                    "intro_iterations": 1,
                    "recurring": settings.IND_6M_RECUR_MONTHLY,
                    "interval": "1mo",
                },
            }

            mapped = plan_map.get(plan or "")
            schedule_id = None
            if mapped and mapped["intro"] and mapped["recurring"]:
                try:
                    # Ensure a schedule exists for this subscription
                    sub = stripe.Subscription.retrieve(subscription_id)
                    existing_schedule = sub.get("schedule")
                    if existing_schedule:
                        schedule_id = existing_schedule if isinstance(existing_schedule, str) else existing_schedule.get("id")
                    else:
                        sched = stripe.SubscriptionSchedule.create(from_subscription=subscription_id)
                        schedule_id = sched.get("id")

                    # Retrieve schedule to anchor phases properly
                    schedule_obj = stripe.SubscriptionSchedule.retrieve(schedule_id)
                    current_phase = schedule_obj.get("current_phase") or {}
                    current_start = current_phase.get("start_date")

                    # Build phases; use current_start if present to avoid changing current phase start
                    intro_phase = {
                        "items": [{"price": mapped["intro"]}],
                        "iterations": mapped.get("intro_iterations", 1),
                    }
                    if current_start:
                        intro_phase["start_date"] = current_start
                    else:
                        # Fallback for schedules without an anchor
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
                    # Audit success with key identifiers
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
                    # Log but do not fail the webhook
                    log("subscription_schedule_update", metadata, "error", str(sched_err))

            # 3) Persist Stripe IDs and schedule metadata + diagnostics
            _controller().db.plans.update_one(
                {"individual_id": role_entity_id},
                {
                    "$set": {
                        "stripe_customer_id": customer_id,
                        "stripe_subscription_id": subscription_id,
                        "stripe_schedule_id": schedule_id,
                        "intro_price_id": mapped["intro"] if mapped else None,
                        "recurring_price_id": mapped["recurring"] if mapped else None,
                        "recurring_interval": mapped["interval"] if mapped else None,
                        "last_checkout_session_id": session.get("id"),
                        "last_event_id": event.get("id"),
                        "updated_at": datetime.utcnow(),
                    },
                    "$setOnInsert": {
                        "id": __import__("uuid").uuid4().hex,
                        "individual_id": role_entity_id,
                        "plan_type": plan,
                        "status": PlanStatus.ACTIVE.value,
                        "selected_services": [],
                        "memory_stack": [],
                        "created_at": datetime.utcnow(),
                    },
                },
                upsert=True,
            )
            try:
                logger.info("plan_persisted", extra={"individual_id": role_entity_id, "subscription_id": subscription_id, "schedule_id": schedule_id})
            except Exception:
                pass
            # Observability: status transition to ACTIVE triggered by checkout completion
            try:
                log("plan_status_transition", {
                    "role": role,
                    "role_entity_id": role_entity_id,
                    "new_status": PlanStatus.ACTIVE.value,
                    "stripe_subscription_id": subscription_id,
                    "stripe_schedule_id": schedule_id,
                    "event_id": event.get("id"),
                }, "ok")
            except Exception:
                pass

        # Record initial payment in payments collection (amount_total is present in session)
        try:
            payments_col = _controller().db["payments"]
            payments_col.create_index("stripe_checkout_session_id", unique=True)

            amount = session.get("amount_total")
            currency = session.get("currency")
            # If Checkout Session lacks totals (some API versions), try to derive from latest invoice on the subscription
            if (amount is None or currency is None) and subscription_id:
                try:
                    sub = stripe.Subscription.retrieve(subscription_id, expand=["latest_invoice"])
                    latest_invoice = sub.get("latest_invoice")
                    if isinstance(latest_invoice, dict):
                        amount = latest_invoice.get("amount_paid") or latest_invoice.get("amount_due")
                        currency = latest_invoice.get("currency")
                except Exception:
                    pass

            payments_col.update_one(
                {"stripe_checkout_session_id": session["id"]},
                {"$set": {
                    "stripe_checkout_session_id": session["id"],
                    "stripe_customer_id": customer_id,
                    "stripe_subscription_id": subscription_id,
                    "role": role,
                    "role_entity_id": role_entity_id,
                    "plan_type": plan,
                    "cycle": cycle,
                    "amount": amount,
                    "currency": currency,
                    "status": session.get("payment_status"),
                    "payment_status": session.get("payment_status"),
                    "payment_source": "checkout_completed",
                    "webhook_event_type": event["type"],
                    "webhook_event_id": event["id"],
                    "stripe_created": datetime.fromtimestamp(session.get("created")),
                    "paid_at": datetime.utcnow() if session.get("payment_status") == "paid" else None,
                }},
                upsert=True,
            )
            try:
                logger.info("payment_recorded", extra={"session_id": session.get("id"), "subscription_id": subscription_id})
            except Exception:
                pass
        except Exception as pay_err:
            log("payment_record", metadata, "error", str(pay_err))
        # No generic metrics write
        # Mark processed in idempotency doc and attach role_entity_id
        try:
            db.webhook_checkouts.update_one(
                {"session_id": session_id},
                {"$set": {"processed": True, "processed_at": datetime.utcnow(), "email": buyer_email, "role_entity_id": role_entity_id}},
            )
        except Exception:
            pass
        log("checkout_completed", {**metadata, "session_id": session_id}, "ok")
        logger.info("checkout_completed", extra={"session_id": session_id, "subscription_id": subscription_id, "customer_id": customer_id})
    except Exception as e:
        log("checkout_completed", {**metadata, "session_id": session.get("id")}, "error", str(e))
        raise


# ---------------------------------------------------------------------------
# Additional webhook handlers
# ---------------------------------------------------------------------------

async def handle_invoice_payment_failed(event):
    """Handle failed payment attempts.

    Strategy:
    1. Log the event for auditing.
    2. If we can identify the owner (via metadata or client_reference_id), mark the
       corresponding plan as *suspended* so that application logic can restrict
       access until payment succeeds.
    """
    invoice = event["data"]["object"]
    metadata = invoice.get("metadata", {})

    # Attempt to extract identifiers – may vary depending on Stripe settings
    role = metadata.get("role")
    role_entity_id = metadata.get("role_entity_id")

    try:
        # if role == UserRole.HOSPITAL.value:
        #     controller.db.plans.update_one(
        #         {"hospital_id": role_entity_id},
        #         {"$set": {"status": PlanStatus.SUSPENDED.value, "updated_at": datetime.utcnow()}},
        #     )
        # elif role == UserRole.INDIVIDUAL.value:
        if role == UserRole.INDIVIDUAL.value:
            _controller().db.plans.update_one(
                {"individual_id": role_entity_id},
                {"$set": {"status": PlanStatus.PAST_DUE.value, "last_event_id": event.get("id"), "updated_at": datetime.utcnow()}},
            )
            # Observability
            log("plan_status_transition", {
                "role": role,
                "role_entity_id": role_entity_id,
                "new_status": PlanStatus.PAST_DUE.value,
                "stripe_customer_id": invoice.get("customer"),
                "stripe_subscription_id": invoice.get("subscription"),
                "event_id": event.get("id"),
            }, "ok")
        log("invoice_payment_failed", metadata, "ok")
    except Exception as e:
        log("invoice_payment_failed", metadata, "error", str(e))
        raise


async def handle_invoice_payment_succeeded(event):
    """Mark plan as active on successful payment."""
    invoice = event["data"]["object"]
    metadata = invoice.get("metadata", {})
    role = metadata.get("role")
    role_entity_id = metadata.get("role_entity_id")
    try:
        # if role == UserRole.HOSPITAL.value:
        #     controller.db.plans.update_one(
        #         {"hospital_id": role_entity_id},
        #         {"$set": {"status": PlanStatus.ACTIVE.value, "updated_at": datetime.utcnow()}},
        #     )
        # elif role == UserRole.INDIVIDUAL.value:
        if role == UserRole.INDIVIDUAL.value:
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

        # --------------------------------------------------------------
        # Persist payment record in "payments" collection
        # --------------------------------------------------------------
        try:
            payment_intent_id = invoice.get("payment_intent")
            charge_id = None
            payment_intent = None
            charge = None

            if payment_intent_id:
                payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id, expand=["charges.data.balance_transaction"])
                if payment_intent.charges and payment_intent.charges.data:
                    charge = payment_intent.charges.data[0]
                    charge_id = charge.id

            amount = invoice.get("amount_due") or 0
            currency = invoice.get("currency")
            amount_received = invoice.get("amount_paid") or 0

            # Balance transaction fees / net
            net_amount = None
            fee_amount = None
            if charge and charge.balance_transaction:
                bal_txn = charge.balance_transaction if isinstance(charge.balance_transaction, dict) else None
                if not bal_txn:
                    bal_txn = stripe.BalanceTransaction.retrieve(charge.balance_transaction)
                net_amount = bal_txn.get("net")
                fee_amount = bal_txn.get("fee")

            payments_col = _controller().db["payments"]
            payments_col.create_index("stripe_invoice_id", unique=True)

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
                    "plan_type": metadata.get("plan_type"),
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
                    "payment_method": {
                        "type": charge.payment_method_details.type if charge else None,
                        "card": {
                            "brand": charge.payment_method_details.card.brand if charge and charge.payment_method_details.type == "card" else None,
                            "last4": charge.payment_method_details.card.last4 if charge and charge.payment_method_details.type == "card" else None,
                            "exp_month": charge.payment_method_details.card.exp_month if charge and charge.payment_method_details.type == "card" else None,
                            "exp_year": charge.payment_method_details.card.exp_year if charge and charge.payment_method_details.type == "card" else None,
                            "fingerprint": charge.payment_method_details.card.fingerprint if charge and charge.payment_method_details.type == "card" else None,
                            "country": charge.payment_method_details.card.country if charge and charge.payment_method_details.type == "card" else None,
                            "funding": charge.payment_method_details.card.funding if charge and charge.payment_method_details.type == "card" else None,
                        } if charge and charge.payment_method_details.type == "card" else None,
                    } if charge else None,
                    "subscription_details": {
                        "plan_type": metadata.get("plan_type"),
                        "plan_cycle": metadata.get("billing_cycle", "monthly"),
                        "period_start": datetime.fromtimestamp(invoice.get("period_start")) if invoice.get("period_start") else None,
                        "period_end": datetime.fromtimestamp(invoice.get("period_end")) if invoice.get("period_end") else None,
                        "is_trial": invoice.get("billing_reason") == "subscription_create" and invoice.get("amount_paid") == 0,
                    },
                    "metadata": {
                        "plan_name": invoice.get("lines", {}).get("data", [{}])[0].get("plan", {}).get("nickname") if invoice.get("lines") else None,
                        "tax_amount": invoice.get("tax"),
                    },
                    "paid_at": datetime.utcnow(),
                    "stripe_created": datetime.fromtimestamp(invoice.get("created")),
                    "payment_source": "invoice_payment_succeeded",
                    "webhook_event_type": event["type"],
                    "webhook_event_id": event["id"],
                }},
                upsert=True,
            )
        except Exception as db_err:
            # Log but do not fail webhook
            log("payment_record", metadata, "error", str(db_err))

        log("invoice_payment_succeeded", metadata, "ok")
    except Exception as e:
        log("invoice_payment_succeeded", metadata, "error", str(e))
        raise


async def handle_subscription_updated(event):
    """Handle subscription status/plan changes (upgrades, downgrades, pauses)."""
    subscription = event["data"]["object"]
    metadata = subscription.get("metadata", {})
    role = metadata.get("role")
    role_entity_id = metadata.get("role_entity_id")

    status = subscription.get("status")
    try:
        # Map Stripe status -> internal PlanStatus
        if status == "active":
            new_status = PlanStatus.ACTIVE
        elif status == "past_due":
            new_status = PlanStatus.PAST_DUE
        elif status in ["unpaid", "paused"]:
            new_status = PlanStatus.SUSPENDED
        elif status == "canceled":
            new_status = PlanStatus.CANCELLED
        else:
            # Default to current behavior: treat unknown as ACTIVE (non-breaking)
            new_status = PlanStatus.ACTIVE

        # if role == UserRole.HOSPITAL.value:
        #     controller.db.plans.update_one(
        #         {"hospital_id": role_entity_id},
        #         {"$set": {"status": new_status.value}},
        #     )
        # elif role == UserRole.INDIVIDUAL.value:
        if role == UserRole.INDIVIDUAL.value:
            _controller().db.plans.update_one(
                {"individual_id": role_entity_id},
                {"$set": {"status": new_status.value, "last_event_id": event.get("id"), "updated_at": datetime.utcnow()}},
            )
        # Observability
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


async def handle_subscription_deleted(event):
    """Handle subscription cancellations (deleted)."""
    subscription = event["data"]["object"]
    metadata = subscription.get("metadata", {})
    role = metadata.get("role")
    role_entity_id = metadata.get("role_entity_id")

    try:
        # if role == UserRole.HOSPITAL.value:
        #     controller.db.plans.update_one(
        #         {"hospital_id": role_entity_id},
        #         {"$set": {"status": PlanStatus.CANCELLED.value}},
        #     )
        # elif role == UserRole.INDIVIDUAL.value:
        if role == UserRole.INDIVIDUAL.value:
            _controller().db.plans.update_one(
                {"individual_id": role_entity_id},
                {"$set": {"status": PlanStatus.CANCELLED.value, "last_event_id": event.get("id"), "updated_at": datetime.utcnow()}},
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


# ---------------------------------------------------------------------------
# Dispatch map must be defined after handler functions
# ---------------------------------------------------------------------------

dispatch_map = {
    "checkout.session.completed": handle_checkout_completed,
    "invoice.payment_failed": handle_invoice_payment_failed,
    "invoice.payment_succeeded": handle_invoice_payment_succeeded,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
}


async def dispatch(event):
    # Entry log for observability (no sensitive data)
    try:
        log("webhook_received", {"type": event.get("type"), "event_id": event.get("id")}, "ok")
    except Exception:
        pass

    # Idempotency guard: record event ID and short-circuit if already processed
    try:
        eid = event.get("id")
        ledger = _controller().db["stripe_events_processed"]
        # Ensure an index for fast lookups and uniqueness
        try:
            ledger.create_index("event_id", unique=True)
        except Exception:
            pass
        # Attempt to insert if missing; if it already exists, matchedCount=1 and upserted_id=None
        res = ledger.update_one(
            {"event_id": eid},
            {"$setOnInsert": {"event_id": eid, "created_at": datetime.utcnow() }},
            upsert=True,
        )
        if res.upserted_id is None:
            # Already seen – increment replay counter and skip
            try:
                ledger.update_one({"event_id": eid}, {"$inc": {"replay_count": 1}, "$set": {"last_seen_at": datetime.utcnow()}})
            except Exception:
                pass
            log("webhook_idempotent_skip", {"event_id": eid, "type": event.get("type")}, "ok")
            return
    except Exception as idemp_err:
        # If the ledger fails, proceed anyway (defense in depth elsewhere)
        log("webhook_idempotency", {"type": event.get("type")}, "error", str(idemp_err))

    etype = event["type"]
    handler = dispatch_map.get(etype)
    if handler:
        await handler(event)
        # Record processed key for visibility/TTL purposes (best-effort)
        try:
            mark_processed(event.get("id"))
        except Exception:
            pass 
