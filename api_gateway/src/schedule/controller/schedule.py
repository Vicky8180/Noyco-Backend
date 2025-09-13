# ============================================================================
# controllers/schedule.py - Schedule Controller
# ============================================================================

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import uuid4
import pytz
from bson import ObjectId
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

from .tracking import TrackingController
from api_gateway.database.db import get_database
from ..schema import (
    CallSchedule, ActiveSchedule, CreateScheduleRequest, UpdateScheduleRequest,
    ScheduleResponse, ScheduleStatsResponse, ScheduleListResponse,
    CallStatus, RepeatType, ScheduleAction, OutboundCallRequest
)
from ...phone.controllers.outbound import OutboundController
from ..services.scheduler_service import SchedulerService

logger = logging.getLogger(__name__)
# Set up more detailed logging for debugging
logging.basicConfig(level=logging.INFO)
logging.getLogger('apscheduler').setLevel(logging.WARNING)  # Suppress debug logs

# Also suppress the schedule controller logs during startup
schedule_logger = logging.getLogger(__name__)
schedule_logger.setLevel(logging.WARNING)


class ScheduleController:
    def __init__(self, outbound_controller):
        self.db = get_database()
        self.scheduler_service = SchedulerService()
        self.outbound_controller = outbound_controller
        self.tracking_controller = TrackingController()
        self._initialized = False

    async def ensure_initialized(self):
        """Ensure the scheduler service is initialized (lazy initialization)"""
        if not self._initialized:
            try:
                # Start the scheduler service
                await self.scheduler_service.start()
                
                # Load existing schedules on startup
                await self._load_existing_schedules()
                
                self._initialized = True
                logger.info("ScheduleController initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize ScheduleController: {e}")
                raise

    def _convert_objectid_to_str(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert MongoDB ObjectId to string in a document"""
        if doc is None:
            return doc
        
        if isinstance(doc, dict):
            for key, value in doc.items():
                if isinstance(value, ObjectId):
                    doc[key] = str(value)
                elif isinstance(value, dict):
                    doc[key] = self._convert_objectid_to_str(value)
                elif isinstance(value, list):
                    doc[key] = [self._convert_objectid_to_str(item) if isinstance(item, dict) else str(item) if isinstance(item, ObjectId) else item for item in value]
        
        # Remove MongoDB _id field
        doc.pop("_id", None)
        return doc

    async def _load_existing_schedules(self):
        """Load existing active schedules from database and add to scheduler"""
        try:
            # Use list() instead of to_list() for synchronous cursor operations
            active_schedules = list(self.db.active_schedules.find({
                "is_paused": False,
                "schedule_action": ScheduleAction.ACTIVE.value,
                "next_run_time": {"$gte": datetime.utcnow()}
            }))

            logger.info(f"Found {len(active_schedules)} active schedules to load")
            for schedule in active_schedules:
                await self._add_job_to_scheduler(schedule)

        except Exception as e:
            logger.error(f"Error loading existing schedules: {e}")

    async def create_schedule(self, request: CreateScheduleRequest) -> ScheduleResponse:
        """Create a new call schedule"""
        try:
            # Ensure scheduler is initialized
            await self.ensure_initialized()
            
            # Create schedule document
            schedule_id = str(uuid4())
            schedule = CallSchedule(
                id=schedule_id,
                created_by=request.created_by,
                user_profile_id=request.user_profile_id,
                agent_instance_id=request.agent_instance_id,
                schedule_time=request.schedule_time,
                repeat_type=request.repeat_type,
                repeat_interval=request.repeat_interval,
                repeat_unit=request.repeat_unit,
                repeat_days=request.repeat_days,
                phone=request.phone,
                condition=request.condition,
                notes=request.notes
            )

            # Save to database - remove await for insert_one
            self.db.call_schedules.insert_one(schedule.dict())
            logger.info(f"Created new schedule: {schedule_id}")

            # Create active schedule
            active_schedule = await self._create_active_schedule(schedule)
            logger.info(f"Created active schedule for: {schedule_id}")

            # Add to scheduler
            await self._add_job_to_scheduler(active_schedule)
            logger.info(f"Added job to scheduler for: {schedule_id}")

            return ScheduleResponse(
                id=schedule_id,
                status="success",
                message="Schedule created successfully",
                schedule=schedule
            )

        except Exception as e:
            logger.error(f"Error creating schedule: {e}")
            return ScheduleResponse(
                id="",
                status="error",
                message=f"Failed to create schedule: {str(e)}"
            )

    async def _create_active_schedule(self, schedule: CallSchedule) -> Dict[str, Any]:
        """Create active schedule entry"""
        active_schedule = ActiveSchedule(
            id=str(uuid4()),
            created_by=schedule.created_by,
            call_schedule_id=schedule.id,
            user_profile_id=schedule.user_profile_id,
            agent_instance_id=schedule.agent_instance_id,
            next_run_time=schedule.schedule_time
        )

        # Remove await for insert_one
        self.db.active_schedules.insert_one(active_schedule.dict())
        return active_schedule.dict()

    async def _add_job_to_scheduler(self, active_schedule: Dict[str, Any]):
        """Add job to APScheduler"""
        try:
            job_id = f"call_{active_schedule['call_schedule_id']}"
            logger.info(f"Adding job to scheduler: {job_id}")

            # Get the actual schedule details for logging
            schedule = self.db.call_schedules.find_one({"id": active_schedule['call_schedule_id']})
            if not schedule:
                logger.error(f"Could not find schedule {active_schedule['call_schedule_id']} to add to scheduler")
                return

            # Schedule the call using scheduler service
            next_run_time = active_schedule['next_run_time']

            # Log original timezone info for debugging
            tz_info = next_run_time.tzinfo if hasattr(next_run_time, 'tzinfo') else "No timezone"
            logger.info(f"Scheduling call {job_id} for {next_run_time.isoformat()} (timezone: {tz_info}) to {schedule['phone']}")

            # Use scheduler service to schedule the call
            success = await self.scheduler_service.schedule_call(
                job_id=job_id,
                run_time=next_run_time,
                callback_func=self._execute_scheduled_call,
                args=(active_schedule['call_schedule_id'],)
            )

            if success:
                logger.info(f"Successfully scheduled call {job_id} for {next_run_time.isoformat()}")
            else:
                logger.error(f"Failed to schedule call {job_id}")

        except Exception as e:
            logger.error(f"Error adding job to scheduler: {e}", exc_info=True)

    async def _execute_scheduled_call(self, schedule_id: str):
        """Execute a scheduled call"""
        try:
            logger.info(f"Executing scheduled call for schedule_id: {schedule_id}")

            # Get schedule details - remove await for find_one
            schedule = self.db.call_schedules.find_one({"id": schedule_id})
            if not schedule:
                logger.error(f"Schedule {schedule_id} not found")
                return

            # Check if schedule is still active
            if schedule.get("schedule_action") != ScheduleAction.ACTIVE.value:
                logger.info(f"Schedule {schedule_id} is not active, skipping")
                return

            # Log before making the call
            logger.info(f"Making outbound call to {schedule['phone']} for schedule {schedule_id}")

            # Create outbound call request using new schema
            call_request = OutboundCallRequest(
                to_number=schedule["phone"],
                user_profile_id=schedule["user_profile_id"],
                created_by=schedule["created_by"],
                agent_instance_id=schedule["agent_instance_id"],
                message=f"Scheduled call for user profile {schedule['user_profile_id']}",
                record=True
            )

            # Make the call
            call_response = await self.outbound_controller.make_call(call_request)
            logger.info(f"Call response for schedule {schedule_id}: {call_response.status}, SID: {call_response.call_sid}")

            # Update schedule with call result - remove await for update_one
            self.db.call_schedules.update_one(
                {"id": schedule_id},
                {
                    "$set": {
                        "call_id": call_response.call_sid,
                        "status": CallStatus.PENDING.value,  # Set to pending, will be updated via webhook
                        "last_attempt_time": datetime.utcnow()
                    }
                }
            )
            
            # Log the call using tracking controller with PENDING status initially
            call_status = CallStatus.PENDING.value  # Start with pending status
            
            # Get information from new schema
            user_profile_id = schedule.get("user_profile_id", "")
            created_by = schedule.get("created_by", "")
            agent_instance_id = schedule.get("agent_instance_id", "")
            phone = schedule.get("phone")
            
            # Log the call with tracking controller
            try:
                await self.tracking_controller.log_call(
                    user_profile_id=user_profile_id,
                    phone=phone,
                    call_type="outgoing",
                    status=call_status,
                    created_by=created_by,
                    agent_instance_id=agent_instance_id,
                    call_id=call_response.call_sid,
                    notes=f"Scheduled call for user profile {user_profile_id}",
                    start_time=datetime.utcnow(),  # Record when the call was initiated
                    conversation_id=None  # Will be updated later via webhook if available
                )
                logger.info(f"Successfully logged call {call_response.call_sid} to tracking system")
            except Exception as e:
                logger.error(f"Error logging call to tracking system: {e}", exc_info=True)

            # Handle repeat scheduling
            await self._handle_repeat_scheduling(schedule)

        except Exception as e:
            logger.error(f"Error executing scheduled call {schedule_id}: {e}", exc_info=True)

            # Update schedule status to failed - remove await for update_one
            self.db.call_schedules.update_one(
                {"id": schedule_id},
                {"$set": {"status": CallStatus.FAILED.value}}
            )

    async def _handle_repeat_scheduling(self, schedule: Dict[str, Any]):
        """Handle repeat scheduling logic"""
        try:
            repeat_type = schedule.get("repeat_type", RepeatType.ONCE.value)

            if repeat_type == RepeatType.ONCE.value:
                # Remove from active schedules - remove await for delete_one
                self.db.active_schedules.delete_one({"call_schedule_id": schedule["id"]})
                return

            # Calculate next run time
            next_run_time = None
            current_time = datetime.utcnow()

            if repeat_type == RepeatType.DAILY.value:
                next_run_time = current_time + timedelta(days=1)
            elif repeat_type == RepeatType.WEEKLY.value:
                next_run_time = current_time + timedelta(weeks=1)
            elif repeat_type == RepeatType.MONTHLY.value:
                next_run_time = current_time + timedelta(days=30)
            elif repeat_type == RepeatType.CUSTOM.value:
                interval = schedule.get("repeat_interval", 1)
                unit = schedule.get("repeat_unit", "days")
                
                # Calculate next run time based on unit
                if unit == "minutes":
                    next_run_time = current_time + timedelta(minutes=interval)
                elif unit == "hours":
                    next_run_time = current_time + timedelta(hours=interval)
                elif unit == "days":
                    next_run_time = current_time + timedelta(days=interval)
                elif unit == "weeks":
                    next_run_time = current_time + timedelta(weeks=interval)
                elif unit == "months":
                    # Approximation for months (30 days per month)
                    next_run_time = current_time + timedelta(days=30*interval)

            if next_run_time:
                # Update active schedule - remove await for update_one
                self.db.active_schedules.update_one(
                    {"call_schedule_id": schedule["id"]},
                    {"$set": {"next_run_time": next_run_time}}
                )

                # Add new job to scheduler
                active_schedule = self.db.active_schedules.find_one({"call_schedule_id": schedule["id"]})
                if active_schedule:
                    await self._add_job_to_scheduler(active_schedule)

        except Exception as e:
            logger.error(f"Error handling repeat scheduling: {e}")

    async def get_schedule_stats(self, user_profile_id: Optional[str] = None, created_by: Optional[str] = None) -> ScheduleStatsResponse:
        """Get schedule statistics"""
        try:
            filter_query = {}
            
            # Filter by user profile or creator
            if user_profile_id:
                filter_query["user_profile_id"] = user_profile_id
            if created_by:
                filter_query["created_by"] = created_by

            # Get schedule counts by status
            pipeline = [
                {"$match": filter_query},
                {"$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }}
            ]

            # Use list() instead of to_list() for aggregate operations
            status_counts = {doc["_id"]: doc["count"] for doc in list(self.db.call_schedules.aggregate(pipeline))}

            # Get active schedule counts
            active_filter = {"is_paused": False}
            if user_profile_id:
                active_filter["user_profile_id"] = user_profile_id
            if created_by:
                active_filter["created_by"] = created_by
                
            active_count = self.db.active_schedules.count_documents(active_filter)

            paused_count = self.db.active_schedules.count_documents({"is_paused": True})

            return ScheduleStatsResponse(
                total_scheduled=sum(status_counts.values()),
                pending=status_counts.get(CallStatus.PENDING.value, 0),
                completed=status_counts.get(CallStatus.COMPLETED.value, 0),
                failed=status_counts.get(CallStatus.FAILED.value, 0),
                cancelled=status_counts.get(CallStatus.CANCELLED.value, 0),
                active_schedules=active_count,
                paused_schedules=paused_count
            )

        except Exception as e:
            logger.error(f"Error getting schedule stats: {e}")
            return ScheduleStatsResponse(
                total_scheduled=0, pending=0, completed=0, failed=0, cancelled=0,
                active_schedules=0, paused_schedules=0
            )

    async def get_schedules(self, user_profile_id: Optional[str] = None, created_by: Optional[str] = None, 
                          status: Optional[str] = None, page: int = 1, per_page: int = 10) -> ScheduleListResponse:
        """Get list of schedules with pagination"""
        try:
            filter_query = {"is_deleted": False}
            
            # Filter by user profile or creator
            if user_profile_id:
                filter_query["user_profile_id"] = user_profile_id
            if created_by:
                filter_query["created_by"] = created_by
            if status:
                filter_query["status"] = status

            # Get total count - remove await for count_documents
            total = self.db.call_schedules.count_documents(filter_query)

            # Get schedules with pagination - use list() instead of to_list()
            skip = (page - 1) * per_page
            schedules_data = list(self.db.call_schedules.find(filter_query).skip(skip).limit(per_page))

            # Convert ObjectIds to strings and remove MongoDB _id field
            schedules_data = [self._convert_objectid_to_str(schedule) for schedule in schedules_data]
            
            schedules = [CallSchedule(**schedule) for schedule in schedules_data]

            return ScheduleListResponse(
                schedules=schedules,
                total=total,
                page=page,
                per_page=per_page
            )

        except Exception as e:
            logger.error(f"Error getting schedules: {e}")
            return ScheduleListResponse(schedules=[], total=0, page=page, per_page=per_page)

    async def update_schedule(self, schedule_id: str, request: UpdateScheduleRequest) -> ScheduleResponse:
        """Update an existing schedule"""
        try:
            # Ensure scheduler is initialized
            await self.ensure_initialized()
            
            # Get existing schedule - remove await for find_one
            existing_schedule = self.db.call_schedules.find_one({"id": schedule_id})
            if not existing_schedule:
                logger.error(f"Schedule {schedule_id} not found for update")
                return ScheduleResponse(
                    id=schedule_id,
                    status="error",
                    message="Schedule not found"
                )

            # Prepare update data
            update_data = {}
            for field, value in request.dict(exclude_unset=True).items():
                if value is not None:
                    update_data[field] = value

            logger.info(f"Updating schedule {schedule_id} with data: {update_data}")

            # Update schedule - remove await for update_one
            result = self.db.call_schedules.update_one(
                {"id": schedule_id},
                {"$set": update_data}
            )

            if result.matched_count == 0:
                logger.error(f"Failed to update schedule {schedule_id} - no matching document")
                return ScheduleResponse(
                    id=schedule_id,
                    status="error",
                    message="Failed to update schedule"
                )

            # If schedule action changed, update scheduler
            if "schedule_action" in update_data:
                action_success = await self._handle_schedule_action_change(schedule_id, update_data["schedule_action"])
                if not action_success:
                    return ScheduleResponse(
                        id=schedule_id,
                        status="error",
                        message=f"Failed to execute {update_data['schedule_action']} action"
                    )

            # If schedule time changed, update active schedule
            if "schedule_time" in update_data:
                await self._update_active_schedule_time(schedule_id, update_data["schedule_time"])

            logger.info(f"Schedule {schedule_id} updated successfully")
            return ScheduleResponse(
                id=schedule_id,
                status="success",
                message="Schedule updated successfully"
            )

        except Exception as e:
            logger.error(f"Error updating schedule: {e}")
            return ScheduleResponse(
                id=schedule_id,
                status="error",
                message=f"Failed to update schedule: {str(e)}"
            )

    async def _handle_schedule_action_change(self, schedule_id: str, action: str):
        """Handle schedule action changes"""
        try:
            job_id = f"call_{schedule_id}"
            
            # Check if schedule exists
            existing_schedule = self.db.call_schedules.find_one({"id": schedule_id})
            if not existing_schedule:
                logger.error(f"Schedule {schedule_id} not found for action {action}")
                return False

            if action == ScheduleAction.PAUSE.value:
                # Pause the job using scheduler service
                job_id = f"call_{schedule_id}"
                await self.scheduler_service.pause_job(job_id)
                # Remove await for update_one
                self.db.active_schedules.update_one(
                    {"call_schedule_id": schedule_id},
                    {"$set": {"is_paused": True}}
                )
                self.db.call_schedules.update_one(
                    {"id": schedule_id},
                    {"$set": {"schedule_action": ScheduleAction.PAUSE.value}}
                )
                logger.info(f"Schedule {schedule_id} paused successfully")

            elif action == ScheduleAction.RESUME.value:
                # Resume the job using scheduler service
                job_id = f"call_{schedule_id}"
                await self.scheduler_service.resume_job(job_id)
                # Remove await for update_one
                self.db.active_schedules.update_one(
                    {"call_schedule_id": schedule_id},
                    {"$set": {"is_paused": False}}
                )
                self.db.call_schedules.update_one(
                    {"id": schedule_id},
                    {"$set": {"schedule_action": ScheduleAction.ACTIVE.value}}
                )
                logger.info(f"Schedule {schedule_id} resumed successfully")

            elif action == ScheduleAction.CANCEL.value:
                # Cancel the job using scheduler service
                job_id = f"call_{schedule_id}"
                await self.scheduler_service.cancel_job(job_id)
                # Remove await for delete_one and update_one
                self.db.active_schedules.delete_one({"call_schedule_id": schedule_id})
                self.db.call_schedules.update_one(
                    {"id": schedule_id},
                    {"$set": {
                        "status": CallStatus.CANCELLED.value,
                        "schedule_action": ScheduleAction.CANCEL.value
                    }}
                )
                logger.info(f"Schedule {schedule_id} cancelled successfully")
            
            return True

        except Exception as e:
            logger.error(f"Error handling schedule action change: {e}")
            return False

    async def _update_active_schedule_time(self, schedule_id: str, new_time: datetime):
        """Update active schedule time"""
        try:
            # Update active schedule - remove await for update_one
            self.db.active_schedules.update_one(
                {"call_schedule_id": schedule_id},
                {"$set": {"next_run_time": new_time}}
            )

            # Update scheduler job
            active_schedule = self.db.active_schedules.find_one({"call_schedule_id": schedule_id})
            if active_schedule:
                await self._add_job_to_scheduler(active_schedule)

        except Exception as e:
            logger.error(f"Error updating active schedule time: {e}")

    async def cancel_pending_schedules(self, user_profile_id: Optional[str] = None, created_by: Optional[str] = None) -> Dict[str, Any]:
        """Cancel all pending schedules"""
        try:
            filter_query = {
                "status": CallStatus.PENDING.value,
                "schedule_action": ScheduleAction.ACTIVE.value
            }

            # Filter by user profile or creator
            if user_profile_id:
                filter_query["user_profile_id"] = user_profile_id
            if created_by:
                filter_query["created_by"] = created_by

            # Get pending schedules - use list() instead of to_list()
            pending_schedules = list(self.db.call_schedules.find(filter_query))

            cancelled_count = 0
            for schedule in pending_schedules:
                # Remove from scheduler using scheduler service
                job_id = f"call_{schedule['id']}"
                await self.scheduler_service.cancel_job(job_id)

                # Update schedule status - remove await for update_one
                self.db.call_schedules.update_one(
                    {"id": schedule["id"]},
                    {"$set": {
                        "status": CallStatus.CANCELLED.value,
                        "schedule_action": ScheduleAction.CANCEL.value
                    }}
                )

                # Remove from active schedules - remove await for delete_one
                self.db.active_schedules.delete_one({"call_schedule_id": schedule["id"]})
                cancelled_count += 1

            return {
                "status": "success",
                "message": f"Cancelled {cancelled_count} pending schedules",
                "cancelled_count": cancelled_count
            }

        except Exception as e:
            logger.error(f"Error cancelling pending schedules: {e}")
            return {
                "status": "error",
                "message": f"Failed to cancel schedules: {str(e)}",
                "cancelled_count": 0
            }

    async def delete_schedule(self, schedule_id: str) -> ScheduleResponse:
        """Completely delete a schedule"""
        try:
            # Ensure scheduler is initialized
            await self.ensure_initialized()
            
            # Remove from scheduler using scheduler service
            job_id = f"call_{schedule_id}"
            await self.scheduler_service.cancel_job(job_id)

            # Completely delete schedule from database - remove await for delete_one
            result = self.db.call_schedules.delete_one({"id": schedule_id})
            
            if result.deleted_count == 0:
                return ScheduleResponse(
                    id=schedule_id,
                    status="error",
                    message="Schedule not found"
                )

            # Remove from active schedules - remove await for delete_one
            self.db.active_schedules.delete_one({"call_schedule_id": schedule_id})

            logger.info(f"Schedule {schedule_id} completely deleted from database")

            return ScheduleResponse(
                id=schedule_id,
                status="success",
                message="Schedule deleted successfully"
            )

        except Exception as e:
            logger.error(f"Error deleting schedule: {e}")
            return ScheduleResponse(
                id=schedule_id,
                status="error",
                message=f"Failed to delete schedule: {str(e)}"
            )

    async def get_active_schedules(self, user_profile_id: Optional[str] = None, created_by: Optional[str] = None, 
                                 page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        """Get list of active schedules with pagination"""
        try:
            # Build filter query
            filter_query = {"schedule_action": {"$ne": ScheduleAction.DELETE.value}}
            
            if user_profile_id:
                filter_query["user_profile_id"] = user_profile_id
            if created_by:
                filter_query["created_by"] = created_by

            # Get total count
            total = self.db.active_schedules.count_documents(filter_query)

            # Get active schedules with pagination
            skip = (page - 1) * per_page
            active_schedules = list(self.db.active_schedules.find(filter_query)
                                  .sort("next_run_time", 1)
                                  .skip(skip)
                                  .limit(per_page))

            # Enrich with schedule details
            enriched_schedules = []
            for active_schedule in active_schedules:
                # Get the original schedule details
                schedule_details = self.db.call_schedules.find_one(
                    {"id": active_schedule["call_schedule_id"]}
                )
                
                if schedule_details:
                    # Combine active schedule and original schedule data
                    enriched_schedule = {
                        **active_schedule,
                        "schedule_details": schedule_details,
                        "agent_name": self._get_agent_name(schedule_details.get("agent_instance_id")),
                        "time_until_next": self._calculate_time_until(active_schedule["next_run_time"]),
                        "status": "active" if not active_schedule.get("is_paused") else "paused"
                    }
                    # Convert ObjectIds to strings
                    enriched_schedule = self._convert_objectid_to_str(enriched_schedule)
                    enriched_schedules.append(enriched_schedule)

            return {
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": (total + per_page - 1) // per_page,
                "data": enriched_schedules
            }

        except Exception as e:
            logger.error(f"Error getting active schedules: {e}")
            return {
                "total": 0,
                "page": page,
                "per_page": per_page,
                "total_pages": 0,
                "data": []
            }

    async def get_active_schedule_stats(self, user_profile_id: Optional[str] = None, created_by: Optional[str] = None) -> Dict[str, Any]:
        """Get active schedule statistics"""
        try:
            # Build filter query
            filter_query = {"schedule_action": {"$ne": ScheduleAction.DELETE.value}}
            
            if user_profile_id:
                filter_query["user_profile_id"] = user_profile_id
            if created_by:
                filter_query["created_by"] = created_by

            # Get counts by status
            pipeline = [
                {"$match": filter_query},
                {"$group": {
                    "_id": {
                        "is_paused": "$is_paused",
                        "schedule_action": "$schedule_action"
                    },
                    "count": {"$sum": 1}
                }}
            ]

            status_counts = list(self.db.active_schedules.aggregate(pipeline))
            
            # Process the counts
            active_count = 0
            paused_count = 0
            
            for item in status_counts:
                if item["_id"]["is_paused"]:
                    paused_count += item["count"]
                else:
                    active_count += item["count"]

            # Get upcoming schedules (next 24 hours)
            next_24h = datetime.utcnow() + timedelta(hours=24)
            upcoming_filter = {**filter_query, "next_run_time": {"$lte": next_24h, "$gte": datetime.utcnow()}}
            upcoming_count = self.db.active_schedules.count_documents(upcoming_filter)

            # Get overdue schedules
            overdue_filter = {**filter_query, "next_run_time": {"$lt": datetime.utcnow()}}
            overdue_count = self.db.active_schedules.count_documents(overdue_filter)

            return {
                "total_active": active_count,
                "total_paused": paused_count,
                "upcoming_24h": upcoming_count,
                "overdue": overdue_count,
                "total": active_count + paused_count
            }

        except Exception as e:
            logger.error(f"Error getting active schedule stats: {e}")
            return {
                "total_active": 0,
                "total_paused": 0,
                "upcoming_24h": 0,
                "overdue": 0,
                "total": 0
            }

    def _get_agent_name(self, agent_instance_id: str) -> str:
        """Get human-readable agent name from instance ID"""
        agent_names = {
            "emotional_companion_v1": "Emotional Companion",
            "accountability_buddy_v1": "Accountability Buddy",
            "social_anxiety_v1": "Social Prep Assistant",
            "therapy_checkin_v1": "Therapy Check-in",
            "loneliness_support_v1": "Loneliness Support"
        }
        return agent_names.get(agent_instance_id, agent_instance_id.replace("_", " ").title())

    def _calculate_time_until(self, next_run_time: datetime) -> str:
        """Calculate human-readable time until next run"""
        try:
            now = datetime.utcnow()
            if isinstance(next_run_time, str):
                next_run_time = datetime.fromisoformat(next_run_time.replace("Z", "+00:00"))
            
            diff = next_run_time - now
            
            if diff.total_seconds() < 0:
                return "Overdue"
            
            days = diff.days
            hours = diff.seconds // 3600
            minutes = (diff.seconds % 3600) // 60
            
            if days > 0:
                return f"{days}d {hours}h"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"
                
        except Exception as e:
            logger.error(f"Error calculating time until: {e}")
            return "Unknown"
