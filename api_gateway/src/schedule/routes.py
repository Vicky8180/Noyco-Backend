
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import datetime
import logging
from ..phone.controllers.outbound import OutboundController
from .controller.schedule import ScheduleController
from .controller.tracking import TrackingController
from .schema import (
    CreateScheduleRequest, UpdateScheduleRequest, ScheduleResponse,
    ScheduleStatsResponse, ScheduleListResponse, CallStatsResponse,
    ScheduleAction
)

# Initialize routers
schedule_router = APIRouter(prefix="/schedule", tags=["Call Scheduling"])
tracking_router = APIRouter(prefix="/schedule/tracking", tags=["Call Tracking"])

# Initialize controller instances
outbound_controller_instance = OutboundController()
schedule_controller_instance = ScheduleController(outbound_controller_instance)
tracking_controller_instance = TrackingController()

# Dependency injection function
def get_schedule_controller() -> ScheduleController:
    if schedule_controller_instance is None:
        raise HTTPException(status_code=500, detail="Schedule controller not initialized")
    return schedule_controller_instance


# ============================================================================
# SCHEDULING ENDPOINTS
# ============================================================================

@schedule_router.post("/create", response_model=ScheduleResponse, summary="Create a new call schedule")
async def create_call_schedule(
    request: CreateScheduleRequest,
    controller: ScheduleController = Depends(get_schedule_controller)
):
    """Create a new call schedule"""
    return await controller.create_schedule(request)


@schedule_router.get("/stats", response_model=ScheduleStatsResponse, summary="Get schedule statistics")
async def get_schedule_statistics(
    user_profile_id: Optional[str] = Query(None, description="Filter by user profile ID"),
    created_by: Optional[str] = Query(None, description="Filter by creator assistant ID"),
    controller: ScheduleController = Depends(get_schedule_controller)
):
    """Get schedule statistics including pending, completed, failed, and cancelled calls"""
    return await controller.get_schedule_stats(user_profile_id, created_by)


@schedule_router.get("/list", response_model=ScheduleListResponse, summary="Get list of schedules")
async def get_schedules(
    user_profile_id: Optional[str] = Query(None, description="Filter by user profile ID"),
    created_by: Optional[str] = Query(None, description="Filter by creator assistant ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Items per page"),
    controller: ScheduleController = Depends(get_schedule_controller)
):
    """Get list of schedules with pagination and filtering"""
    return await controller.get_schedules(user_profile_id, created_by, status, page, per_page)


@schedule_router.put("/{schedule_id}", response_model=ScheduleResponse, summary="Update a schedule")
async def update_schedule(
    schedule_id: str,
    request: UpdateScheduleRequest,
    controller: ScheduleController = Depends(get_schedule_controller)
):
    """Update an existing schedule"""
    return await controller.update_schedule(schedule_id, request)


@schedule_router.post("/{schedule_id}/pause", response_model=ScheduleResponse, summary="Pause a schedule")
async def pause_schedule(
    schedule_id: str,
    controller: ScheduleController = Depends(get_schedule_controller)
):
    """Pause a schedule"""
    request = UpdateScheduleRequest(schedule_action=ScheduleAction.PAUSE)
    return await controller.update_schedule(schedule_id, request)


@schedule_router.post("/{schedule_id}/resume", response_model=ScheduleResponse, summary="Resume a schedule")
async def resume_schedule(
    schedule_id: str,
    controller: ScheduleController = Depends(get_schedule_controller)
):
    """Resume a paused schedule"""
    request = UpdateScheduleRequest(schedule_action=ScheduleAction.RESUME)
    return await controller.update_schedule(schedule_id, request)


@schedule_router.post("/{schedule_id}/cancel", response_model=ScheduleResponse, summary="Cancel a schedule")
async def cancel_schedule(
    schedule_id: str,
    controller: ScheduleController = Depends(get_schedule_controller)
):
    """Cancel a schedule"""
    request = UpdateScheduleRequest(schedule_action=ScheduleAction.CANCEL)
    return await controller.update_schedule(schedule_id, request)


@schedule_router.delete("/{schedule_id}", response_model=ScheduleResponse, summary="Delete a schedule")
async def delete_schedule(
    schedule_id: str,
    controller: ScheduleController = Depends(get_schedule_controller)
):
    """Delete a schedule"""
    return await controller.delete_schedule(schedule_id)


@schedule_router.post("/cancel-pending", summary="Cancel all pending schedules")
async def cancel_pending_schedules(
    user_profile_id: Optional[str] = Query(None, description="Filter by user profile ID"),
    created_by: Optional[str] = Query(None, description="Filter by creator assistant ID"),
    controller: ScheduleController = Depends(get_schedule_controller)
):
    """Cancel all pending schedules"""
    return await controller.cancel_pending_schedules(user_profile_id, created_by)


# ============================================================================
# ACTIVE SCHEDULES ENDPOINTS
# ============================================================================

@schedule_router.get("/active/list", summary="Get list of active schedules")
async def get_active_schedules(
    user_profile_id: Optional[str] = Query(None, description="Filter by user profile ID"),
    created_by: Optional[str] = Query(None, description="Filter by creator assistant ID"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Items per page"),
    controller: ScheduleController = Depends(get_schedule_controller)
):
    """Get list of active schedules with pagination and filtering"""
    return await controller.get_active_schedules(user_profile_id, created_by, page, per_page)


@schedule_router.get("/active/stats", summary="Get active schedule statistics")
async def get_active_schedule_stats(
    user_profile_id: Optional[str] = Query(None, description="Filter by user profile ID"),
    created_by: Optional[str] = Query(None, description="Filter by creator assistant ID"),
    controller: ScheduleController = Depends(get_schedule_controller)
):
    """Get active schedule statistics"""
    return await controller.get_active_schedule_stats(user_profile_id, created_by)


# ============================================================================
# TRACKING ENDPOINTS
# ============================================================================

@tracking_router.get("/stats", response_model=CallStatsResponse, summary="Get call statistics")
async def get_call_statistics(
    user_profile_id: Optional[str] = Query(None, description="Filter by user profile ID"),
    created_by: Optional[str] = Query(None, description="Filter by creator assistant ID"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter")
):
    """Get call statistics including total calls, completion rates, and time distribution"""
    return await tracking_controller_instance.get_call_stats(
        user_profile_id=user_profile_id, 
        created_by=created_by,
        start_date=start_date, 
        end_date=end_date
    )


@tracking_router.get("/history", summary="Get call history")
async def get_call_history(
    user_profile_id: Optional[str] = Query(None, description="Filter by user profile ID"),
    created_by: Optional[str] = Query(None, description="Filter by creator assistant ID"),
    call_type: Optional[str] = Query(None, description="Filter by call type"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Items per page")
):
    """Get call history with pagination and filtering"""
    return await tracking_controller_instance.get_call_history(
        user_profile_id=user_profile_id,
        created_by=created_by,
        call_type=call_type,
        page=page,
        per_page=per_page
    )


@tracking_router.post("/log", summary="Log a call")
async def log_call(
    user_profile_id: str = Query(..., description="User profile ID"),
    phone: str = Query(..., description="Phone number"),
    call_type: str = Query(..., description="Call type (incoming/outgoing)"),
    status: str = Query(..., description="Call status"),
    created_by: str = Query(..., description="Assistant ID who created/initiated the call"),
    call_id: Optional[str] = Query(None, description="Twilio call SID"),
    agent_instance_id: Optional[str] = Query(None, description="Agent instance ID"),
    conversation_id: Optional[str] = Query(None, description="Conversation ID"),
    duration: Optional[int] = Query(None, description="Call duration in seconds"),
    notes: Optional[str] = Query(None, description="Additional notes")
):
    """Log a call manually"""
    return await tracking_controller_instance.log_call(
        user_profile_id=user_profile_id,
        phone=phone,
        call_type=call_type,
        status=status,
        created_by=created_by,
        call_id=call_id,
        agent_instance_id=agent_instance_id,
        conversation_id=conversation_id,
        duration=duration,
        notes=notes
    )


@tracking_router.put("/call/{call_id}/status", summary="Update call status")
async def update_call_status(
    call_id: str,
    status: str = Query(..., description="New call status"),
    duration: Optional[int] = Query(None, description="Call duration in seconds"),
    conversation_id: Optional[str] = Query(None, description="Conversation ID"),
    notes: Optional[str] = Query(None, description="Additional notes")
):
    """Update call status by call ID"""
    return await tracking_controller_instance.update_call_details(
        call_id=call_id,
        status=status,
        duration=duration,
        conversation_id=conversation_id,
        notes=notes
    )
