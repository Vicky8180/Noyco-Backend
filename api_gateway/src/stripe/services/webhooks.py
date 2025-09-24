from datetime import datetime
from ..audit import log
from ...billing.controller import BillingController
from ..client import get_stripe
from ...billing.schema import PlanType, UserRole, PlanStatus, PlanSelectionRequest

stripe = get_stripe()
controller = BillingController()

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
    role_entity_id = metadata.get("role_entity_id")
    plan = _norm(metadata.get("plan"))
    cycle = _norm(metadata.get("billing_cycle", "monthly"))

    try:
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")

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
        # elif role == UserRole.INDIVIDUAL.value:
        if role == UserRole.INDIVIDUAL.value:
            await controller.select_individual_plan(
                individual_id=role_entity_id,
                plan_type=PlanType(plan),
                user_id="stripe-webhook",
            )
            controller.db.plans.update_one(
                {"individual_id": role_entity_id},
                {"$set": {"stripe_customer_id": customer_id, "stripe_subscription_id": subscription_id}},
            )

        # Record initial payment in payments collection (amount_total is present in session)
        try:
            payments_col = controller.db["payments"]
            payments_col.create_index("stripe_checkout_session_id", unique=True)

            payments_col.update_one(
                {"stripe_checkout_session_id": session["id"]},
                {"$set": {
                    "stripe_checkout_session_id": session["id"],
                    "stripe_customer_id": customer_id,
                    "stripe_subscription_id": subscription_id,
                    "user_id": metadata.get("user_id"),
                    "role": role,
                    "role_entity_id": role_entity_id,
                    "plan_type": plan,
                    "cycle": cycle,
                    "amount": session.get("amount_total"),
                    "currency": session.get("currency"),
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
        except Exception as pay_err:
            log("payment_record", metadata, "error", str(pay_err))
        log("checkout_completed", metadata, "ok")
    except Exception as e:
        log("checkout_completed", metadata, "error", str(e))
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
            controller.db.plans.update_one(
                {"individual_id": role_entity_id},
                {"$set": {"status": PlanStatus.SUSPENDED.value, "updated_at": datetime.utcnow()}},
            )
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
            controller.db.plans.update_one(
                {"individual_id": role_entity_id},
                {"$set": {"status": PlanStatus.ACTIVE.value, "updated_at": datetime.utcnow()}},
            )

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

            payments_col = controller.db["payments"]
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
                    "plan_type": metadata.get("plan"),
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
                        "plan_type": metadata.get("plan"),
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
        new_status = PlanStatus.ACTIVE
        if status in ["canceled", "unpaid", "past_due", "paused"]:
            new_status = PlanStatus.SUSPENDED

        # if role == UserRole.HOSPITAL.value:
        #     controller.db.plans.update_one(
        #         {"hospital_id": role_entity_id},
        #         {"$set": {"status": new_status.value}},
        #     )
        # elif role == UserRole.INDIVIDUAL.value:
        if role == UserRole.INDIVIDUAL.value:
            controller.db.plans.update_one(
                {"individual_id": role_entity_id},
                {"$set": {"status": new_status.value}},
            )
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
            controller.db.plans.update_one(
                {"individual_id": role_entity_id},
                {"$set": {"status": PlanStatus.CANCELLED.value}},
            )
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
    etype = event["type"]
    handler = dispatch_map.get(etype)
    if handler:
        await handler(event) 
