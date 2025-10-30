from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Response

from ...middlewares.jwt_auth import JWTAuthController
from ..auth.schema import UserRole
from ..billing.schema import PlanType as IndividualPlanType
from ..metrics.controller import ConversationMetricsController


def _safe_plan_type(value: Optional[str]) -> Optional[str]:
	try:
		if not value:
			return None
		return IndividualPlanType(value).value
	except Exception:
		return value  # allow legacy strings in listings


async def list_users_controller(
	db,
	*,
	page: int,
	per_page: int,
	q: Optional[str],
	status_filter: Optional[str],
	plan: Optional[str],
	subscription_status: Optional[str],
	date_from: Optional[str],
	date_to: Optional[str],
	sort: str,
) -> Dict[str, Any]:
	# Base filter: individual users only
	filt: Dict[str, Any] = {"role": UserRole.INDIVIDUAL.value}

	if q:
		filt["$or"] = [
			{"email": {"$regex": q, "$options": "i"}},
			{"name": {"$regex": q, "$options": "i"}},
		]

	if status_filter == "active":
		filt["is_active"] = True
	elif status_filter == "inactive":
		filt["is_active"] = False

	# Date range based on user created_at
	if date_from or date_to:
		created_at_filter: Dict[str, Any] = {}
		if date_from:
			try:
				created_at_filter["$gte"] = datetime.fromisoformat(date_from)
			except Exception:
				raise HTTPException(status_code=400, detail="Invalid date_from")
		if date_to:
			try:
				created_at_filter["$lte"] = datetime.fromisoformat(date_to)
			except Exception:
				raise HTTPException(status_code=400, detail="Invalid date_to")
		filt["created_at"] = created_at_filter

	# Sorting
	sort_map = {
		"created_at": ("created_at", 1),
		"-created_at": ("created_at", -1),
		"last_login": ("last_login", 1),
		"-last_login": ("last_login", -1),
	}
	sort_field, sort_dir = sort_map.get(sort, ("created_at", -1))

	skip = (page - 1) * per_page
	users = list(db.users.find(filt).sort(sort_field, sort_dir).skip(skip).limit(per_page))

	# Enrich with plan + profiles count + conversation count
	data: List[Dict[str, Any]] = []
	for u in users:
		individual_id = u.get("role_entity_id")
		plan_doc = db.plans.find_one({"individual_id": individual_id}) or {}
		profiles_count = db.user_profiles.count_documents({"role_entity_id": individual_id})
		conversations_count = db.conversations.count_documents({"individual_id": individual_id})

		item = {
			"user_id": u.get("id"),
			"email": u.get("email"),
			"name": u.get("name"),
			"created_at": u.get("created_at"),
			"last_login": u.get("last_login"),
			"is_active": u.get("is_active", True),
			"role_entity_id": individual_id,
			"current_plan": _safe_plan_type(plan_doc.get("plan_type")),
			"subscription_status": plan_doc.get("status"),
			"profiles_count": profiles_count,
			"conversations_count": conversations_count,
		}

		data.append(item)

	# Optional filters that depend on plan data
	if plan:
		# Case-insensitive compare for plan value
		data = [d for d in data if ((d.get("current_plan") or "").lower() == plan.lower())]
	if subscription_status:
		# Normalize American/British spelling and compare case-insensitively
		norm = subscription_status.lower()
		if norm == "canceled":
			norm = "cancelled"
		data = [d for d in data if ((d.get("subscription_status") or "").lower() == norm)]

	return {
		"total": len(data),
		"page": page,
		"per_page": per_page,
		"count": len(data),
		"data": data,
	}


async def get_user_details_controller(db, *, user_id: str) -> Dict[str, Any]:
	u = db.users.find_one({"id": user_id})
	if not u:
		raise HTTPException(status_code=404, detail="User not found")
	if u.get("role") != UserRole.INDIVIDUAL.value:
		raise HTTPException(status_code=400, detail="Only individual users supported")

	individual_id = u.get("role_entity_id")
	individual = db.individuals.find_one({"id": individual_id}) or {}
	plan_doc = db.plans.find_one({"individual_id": individual_id}) or {}
	profiles = list(db.user_profiles.find({"role_entity_id": individual_id}))
	# Stripe audit history (recent)
	audit_events = list(db.stripe_audit.find({"payload.role_entity_id": individual_id}).sort("created_at", -1).limit(50))

	# Conversation summary
	metrics = ConversationMetricsController(db)
	analytics = await metrics.get_conversation_analytics(individual_id)

	# Sanitize audit events (remove ObjectId and large nested payloads)
	safe_audit: List[Dict[str, Any]] = []
	for e in audit_events:
		try:
			evt: Dict[str, Any] = {
				"id": str(e.get("id") or e.get("_id", "")) if (e.get("id") or e.get("_id")) else None,
				"event": e.get("event") or e.get("type") or e.get("action"),
				"status": e.get("status"),
				"created_at": e.get("created_at"),
			}
			payload = e.get("payload")
			if isinstance(payload, dict):
				minimal = {k: payload.get(k) for k in ["role_entity_id", "individual_id", "plan_type", "stripe_customer_id", "stripe_subscription_id"] if k in payload}
				evt["payload"] = minimal
			safe_audit.append(evt)
		except Exception:
			continue

	return {
		"user": {
			"user_id": u.get("id"),
			"email": u.get("email"),
			"name": u.get("name"),
			"created_at": u.get("created_at"),
			"last_login": u.get("last_login"),
			"is_active": u.get("is_active", True),
			"role_entity_id": individual_id,
		},
		"individual": {
			"id": individual.get("id"),
			"phone": individual.get("phone"),
			"onboarding_completed": individual.get("onboarding_completed", False),
			"plan": individual.get("plan"),
		},
		"plan": {
			"plan_type": plan_doc.get("plan_type"),
			"status": plan_doc.get("status"),
			"stripe_customer_id": plan_doc.get("stripe_customer_id"),
			"stripe_subscription_id": plan_doc.get("stripe_subscription_id"),
			"cancel_at_period_end": plan_doc.get("cancel_at_period_end"),
			"current_period_end": plan_doc.get("current_period_end"),
			"updated_at": plan_doc.get("updated_at"),
		} if plan_doc else None,
		"profiles": [
			{
				"user_profile_id": p.get("user_profile_id"),
				"profile_name": p.get("profile_name"),
				"phone": p.get("phone"),
				"created_at": p.get("created_at"),
				"is_active": p.get("is_active", True),
			}
			for p in profiles
		],
		"stripe_audit": safe_audit,
		"conversation_analytics": analytics,
	}


async def get_user_invoices_controller(db, *, user_id: str) -> Dict[str, Any]:
	from ..stripe.client import get_stripe

	u = db.users.find_one({"id": user_id})
	if not u:
		raise HTTPException(status_code=404, detail="User not found")
	individual_id = u.get("role_entity_id")
	plan_doc = db.plans.find_one({"individual_id": individual_id}) or {}
	customer_id = plan_doc.get("stripe_customer_id")
	if not customer_id:
		return {"data": []}

	stripe = get_stripe()
	try:
		invoices = stripe.Invoice.list(customer=customer_id, limit=50)
		try:
			return invoices.to_dict()
		except Exception:
			return {"data": [getattr(inv, "to_dict")() if hasattr(inv, "to_dict") else dict(inv) for inv in getattr(invoices, "data", [])]}
	except Exception as e:
		raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")


async def update_user_status_controller(db, *, user_id: str, is_active: bool) -> Dict[str, Any]:
	result = db.users.update_one({"id": user_id}, {"$set": {"is_active": is_active, "updated_at": datetime.utcnow()}})
	if result.matched_count == 0:
		raise HTTPException(status_code=404, detail="User not found")
	return {"user_id": user_id, "is_active": is_active}


async def impersonate_user_controller(
	db,
	*,
	user_id: str,
	response: Response,
	jwt_auth: JWTAuthController,
) -> Dict[str, Any]:
	u = db.users.find_one({"id": user_id})
	if not u:
		raise HTTPException(status_code=404, detail="User not found")
	if u.get("role") != UserRole.INDIVIDUAL.value:
		raise HTTPException(status_code=400, detail="Only individual users can be impersonated")

	individual_id = u.get("role_entity_id")
	email = u.get("email")

	# Determine plan for token claims (best-effort)
	plan_type = None
	ind = db.individuals.find_one({"id": individual_id}) or {}
	plan_raw = ind.get("plan")
	try:
		plan_type = IndividualPlanType(plan_raw) if plan_raw else None
	except Exception:
		plan_type = None

	access_token = jwt_auth.create_access_token(u["id"], individual_id, UserRole.INDIVIDUAL, email, plan_type)
	refresh_token = jwt_auth.create_refresh_token(u["id"], individual_id)
	csrf_token = jwt_auth.set_auth_cookies(response, access_token, refresh_token)

	return {"success": True, "csrf_token": csrf_token, "user": {"id": u["id"], "email": email, "role_entity_id": individual_id}}


