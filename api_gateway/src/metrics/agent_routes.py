from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from api_gateway.database.db import get_database
from ...middlewares.jwt_auth import JWTAuthController
from ..auth.schema import JWTClaims
from .agent_controller import AgentMetricsController
from .agent_schema import (
    AgentMetricsResponseSchema,
    AgentTypeOptionSchema,
    GoalProgressDataSchema
)

router = APIRouter(prefix="/api/metrics/agents", tags=["Agent Metrics"])
jwt_auth = JWTAuthController()

@router.get("/types", response_model=list[AgentTypeOptionSchema])
async def get_agent_types_with_stats(
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    db = Depends(get_database)
):
    """Get all available agent types with their statistics"""
    controller = AgentMetricsController(db)
    return await controller.get_agent_types_options(current_user.role_entity_id)

@router.get("/{agent_type}/metrics", response_model=AgentMetricsResponseSchema)
async def get_agent_metrics(
    agent_type: str,
    timeframe: str = Query("7d", description="Time range: 1d, 7d, 14d, 30d"),
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    db = Depends(get_database)
):
    """Get comprehensive metrics for a specific agent type"""
    controller = AgentMetricsController(db)
    return await controller.get_agent_metrics(
        individual_id=current_user.role_entity_id,
        agent_type=agent_type,
        timeframe=timeframe
    )

@router.get("/{agent_type}/goals/{goal_id}/progress", response_model=GoalProgressDataSchema)
async def get_goal_progress_data(
    agent_type: str,
    goal_id: str,
    timeframe: str = Query("30d", description="Time range: 7d, 14d, 30d, 90d"),
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    db = Depends(get_database)
):
    """Get detailed progress data for a specific goal"""
    controller = AgentMetricsController(db)
    return await controller.get_goal_progress_data(
        individual_id=current_user.role_entity_id,
        agent_type=agent_type,
        goal_id=goal_id,
        timeframe=timeframe
    )

@router.get("/analytics/summary")
async def get_agents_analytics_summary(
    timeframe: str = Query("30d", description="Time range: 7d, 14d, 30d, 90d"),
    current_user: JWTClaims = Depends(jwt_auth.get_current_user),
    db = Depends(get_database)
):
    """Get summary analytics across all agent types"""
    controller = AgentMetricsController(db)
    return await controller.get_agent_analytics_summary(
        individual_id=current_user.role_entity_id,
        timeframe=timeframe
    )
