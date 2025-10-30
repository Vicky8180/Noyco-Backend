from fastapi import APIRouter, Depends, HTTPException, Query, Response
from typing import Optional, Dict, Any

from ...middlewares.jwt_auth import JWTAuthController
from ..auth.schema import UserRole, JWTClaims
from ...database.db import get_database

from .controller import (
	list_users_controller,
	get_user_details_controller,
	get_user_invoices_controller,
	update_user_status_controller,
	impersonate_user_controller,
)

router = APIRouter(prefix="/admin", tags=["Admin Users"])
jwt_auth = JWTAuthController()


def _admin_only(user: JWTClaims = Depends(jwt_auth.get_current_user)) -> JWTClaims:
	if user.role != UserRole.ADMIN:
		raise HTTPException(status_code=403, detail="Admin access required")
	return user


@router.get("/users")
async def list_users(
	_: JWTClaims = Depends(_admin_only),
	db = Depends(get_database),
	page: int = Query(1, ge=1),
	per_page: int = Query(20, ge=1, le=100),
	q: Optional[str] = Query(None, description="Search by email or name"),
	status_filter: Optional[str] = Query(None, regex="^(active|inactive)$"),
	plan: Optional[str] = Query(None, description="Filter by plan type: one_month|three_months|six_months"),
	subscription_status: Optional[str] = Query(None, description="Plan status: active|pending|canceled|inactive|cancelled|suspended|expired|past_due"),
	date_from: Optional[str] = Query(None, description="ISO date for registration start"),
	date_to: Optional[str] = Query(None, description="ISO date for registration end"),
	sort: str = Query("-created_at", description="Sort: created_at,-created_at,last_login,-last_login"),
):
	return await list_users_controller(
		db,
		page=page,
		per_page=per_page,
		q=q,
		status_filter=status_filter,
		plan=plan,
		subscription_status=subscription_status,
		date_from=date_from,
		date_to=date_to,
		sort=sort,
	)


@router.get("/users/{user_id}")
async def get_user_details(
	user_id: str,
	_: JWTClaims = Depends(_admin_only),
	db = Depends(get_database),
):
	return await get_user_details_controller(db, user_id=user_id)


@router.get("/users/{user_id}/invoices")
async def get_user_invoices(
	user_id: str,
	_: JWTClaims = Depends(_admin_only),
	db = Depends(get_database),
):
	return await get_user_invoices_controller(db, user_id=user_id)


@router.patch("/users/{user_id}/status")
async def update_user_status(
	user_id: str,
	body: Dict[str, Any],
	_: JWTClaims = Depends(_admin_only),
	db = Depends(get_database),
):
	if "is_active" not in body or not isinstance(body.get("is_active"), bool):
		raise HTTPException(status_code=400, detail="Missing or invalid is_active")
	return await update_user_status_controller(db, user_id=user_id, is_active=body["is_active"])


@router.post("/users/{user_id}/impersonate")
async def impersonate_user(
	user_id: str,
	response: Response,
	_: JWTClaims = Depends(_admin_only),
	db = Depends(get_database),
):
	return await impersonate_user_controller(db, user_id=user_id, response=response, jwt_auth=jwt_auth)

