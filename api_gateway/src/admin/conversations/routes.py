from fastapi import APIRouter, Depends, Query
from typing import Optional

from ....middlewares.jwt_auth import JWTAuthController
from ...auth.schema import UserRole, JWTClaims
from ....database.db import get_database

from .controller import (
    list_conversations_controller,
    get_conversation_detail_controller,
    get_agent_types_controller,
)

router = APIRouter(prefix="/admin/conversations", tags=["Admin Conversations"])
jwt_auth = JWTAuthController()


def _admin_only(user: JWTClaims = Depends(jwt_auth.get_current_user)) -> JWTClaims:
    if user.role != UserRole.ADMIN:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/agent-types")
async def get_agent_types(
    _: JWTClaims = Depends(_admin_only),
    db = Depends(get_database),
):
    return await get_agent_types_controller(db)


@router.get("")
async def list_conversations(
    _: JWTClaims = Depends(_admin_only),
    db = Depends(get_database),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    agent_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="active|paused"),
    user: Optional[str] = Query(None, description="user email or user_id"),
):
    return await list_conversations_controller(
        db,
        page=page,
        per_page=per_page,
        agent_type=agent_type,
        status=status,
        user=user,
    )


@router.get("/{conversation_id}")
async def get_conversation_detail(
    conversation_id: str,
    _: JWTClaims = Depends(_admin_only),
    db = Depends(get_database),
    redact: bool = Query(True, description="Redact PII like emails/phones in transcript"),
):
    return await get_conversation_detail_controller(db, conversation_id=conversation_id, redact=redact)
