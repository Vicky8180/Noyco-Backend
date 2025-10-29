from fastapi import APIRouter, Depends, Query
from typing import Optional

from ....middlewares.jwt_auth import JWTAuthController
from ...auth.schema import UserRole, JWTClaims
from ....database.db import get_database
from ...stripe.client import get_stripe
from .controller import (
    get_summary_controller,
    list_cancelled_controller,
    list_failed_payments_controller,
    list_subscriptions_controller,
)

router = APIRouter(prefix="/admin/billing", tags=["Admin Billing"])
jwt_auth = JWTAuthController()


def _admin_only(user: JWTClaims = Depends(jwt_auth.get_current_user)) -> JWTClaims:
    if user.role != UserRole.ADMIN:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/summary")
async def get_billing_summary(
    _: JWTClaims = Depends(_admin_only),
    db = Depends(get_database),
):
    stripe = get_stripe()
    return await get_summary_controller(db, stripe)


@router.get("/subscriptions")
async def get_subscriptions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    status: Optional[str] = Query(None),
    _: JWTClaims = Depends(_admin_only),
    db = Depends(get_database),
):
    return await list_subscriptions_controller(db, page=page, per_page=per_page, status=status)


@router.get("/cancelled")
async def get_cancelled(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    _: JWTClaims = Depends(_admin_only),
    db = Depends(get_database),
):
    return await list_cancelled_controller(db, page=page, per_page=per_page)


@router.get("/failed-payments")
async def get_failed_payments(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    _: JWTClaims = Depends(_admin_only),
    db = Depends(get_database),
):
    return await list_failed_payments_controller(db, page=page, per_page=per_page)
