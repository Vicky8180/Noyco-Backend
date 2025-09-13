from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from api_gateway.database.db import get_database
from ...middlewares.jwt_auth import JWTAuthController
from ..auth.schema import JWTClaims
from .controller import ConversationMetricsController
from .schema import ConversationsResponseSchema, ConversationDetailSchema, AgentTypeSchema

router = APIRouter(prefix="/api/metrics", tags=["Conversation Metrics"])
jwt_auth = JWTAuthController()

@router.get("/agent-types", response_model=list[AgentTypeSchema])
async def get_agent_types(
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    db = Depends(get_database)
):
    """Get all available agent types for the current user"""
    controller = ConversationMetricsController(db)
    return await controller.get_available_agent_types(current_user.role_entity_id)

@router.get("/conversations", response_model=ConversationsResponseSchema)
async def get_conversations(
    agent_type: Optional[str] = Query(None, description="Filter by agent type (e.g., 'loneliness', 'accountability', etc.)"),
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    db = Depends(get_database)
):
    """Get conversations grouped by agent_instance_id, optionally filtered by agent type"""
    controller = ConversationMetricsController(db)
    return await controller.get_conversations_by_agent_type(
        individual_id=current_user.role_entity_id,
        agent_type=agent_type
    )

@router.get("/conversations/{conversation_id}", response_model=ConversationDetailSchema)
async def get_conversation_detail(
    conversation_id: str,
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    db = Depends(get_database)
):
    """Get detailed conversation with full context"""
    controller = ConversationMetricsController(db)
    return await controller.get_conversation_detail(
        conversation_id=conversation_id,
        individual_id=current_user.role_entity_id
    )

@router.get("/analytics")
async def get_conversation_analytics(
    agent_type: Optional[str] = Query(None, description="Filter analytics by agent type"),
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    db = Depends(get_database)
):
    """Get conversation analytics for the user"""
    controller = ConversationMetricsController(db)
    return await controller.get_conversation_analytics(
        individual_id=current_user.role_entity_id,
        agent_type=agent_type
    )

# Legacy endpoint compatibility - redirect to new structure
@router.get("/dashboard")
async def get_dashboard_legacy(
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    db = Depends(get_database)
):
    """Legacy dashboard endpoint - returns analytics data"""
    controller = ConversationMetricsController(db)
    analytics = await controller.get_conversation_analytics(current_user.role_entity_id)
    
    return {
        "conversation_analytics": analytics,
        "call_analytics": {
            "total_calls": 0,
            "success_rate": 0,
            "average_duration": 0
        },
        "system_health": {
            "status": "healthy",
            "uptime": "99.9%",
            "response_time": "1.2s",
            "error_rate": "0.1%"
        }
    }
