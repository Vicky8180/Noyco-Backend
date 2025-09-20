# """
# Status Update Service - Handles call status updates from Twilio webhooks
# Coordinates updates between call logs, schedules, and tracking
# """

# import logging
# from datetime import datetime
# from typing import Dict, Any, Optional
# from uuid import uuid4

# from api_gateway.database.db import get_database
# from ..schema import CallStatus, CallType, CallLog
# from ..controller.tracking import TrackingController

# logger = logging.getLogger(__name__)


# class StatusUpdateService:
#     """Service for handling call status updates from Twilio webhooks"""

#     def __init__(self):
#         self.db = get_database()
#         self.tracking_controller = TrackingController()

#     async def handle_call_status_update(self, call_data: Dict[str, Any]) -> Dict[str, Any]:
#         """
#         Handle call status update from Twilio webhook
#         Updates both call logs and call schedules
#         """
#         try:
#             call_sid = call_data.get("CallSid")
#             call_status = call_data.get("CallStatus")
#             call_duration = call_data.get("CallDuration")
            
#             if not call_sid or not call_status:
#                 logger.error("Missing required fields: CallSid and CallStatus")
#                 return {
#                     "status": "error",
#                     "message": "Missing required fields: CallSid and CallStatus"
#                 }

#             logger.info(f"Processing call status update for {call_sid}: {call_status}")

#             # Parse call duration if available
#             duration = None
#             if call_duration:
#                 try:
#                     duration = int(call_duration)
#                 except (ValueError, TypeError):
#                     logger.warning(f"Invalid call duration: {call_duration}")

#             # Calculate timing information
#             start_time = None
#             end_time = None
            
#             if call_status in ["completed", "failed", "busy", "no-answer", "canceled"]:
#                 end_time = datetime.utcnow()
#                 if duration:
#                     # Calculate start time based on duration
#                     from datetime import timedelta
#                     start_time = end_time - timedelta(seconds=duration)

#             # Update call logs
#             call_log_result = await self.tracking_controller.update_call_details(
#                 call_id=call_sid,
#                 status=call_status,
#                 duration=duration,
#                 start_time=start_time,
#                 end_time=end_time,
#                 notes=f"Status updated via webhook: {call_status}"
#             )

#             # Update call schedule if this call is associated with a schedule
#             schedule_result = await self._update_schedule_status(call_sid, call_status, duration)

#             logger.info(f"Call status update completed for {call_sid}")

#             return {
#                 "status": "success",
#                 "message": f"Call status updated to {call_status}",
#                 "call_log_update": call_log_result,
#                 "schedule_update": schedule_result,
#                 "call_sid": call_sid,
#                 "duration": duration
#             }

#         except Exception as e:
#             logger.error(f"Error handling call status update: {e}", exc_info=True)
#             return {
#                 "status": "error",
#                 "message": f"Failed to handle call status update: {str(e)}"
#             }

#     async def _update_schedule_status(self, call_sid: str, call_status: str, duration: Optional[int] = None) -> Dict[str, Any]:
#         """Update call schedule status based on call outcome"""
#         try:
#             # Find schedule associated with this call
#             schedule = self.db.call_schedules.find_one({"call_id": call_sid})
            
#             if not schedule:
#                 logger.info(f"No schedule found for call {call_sid}")
#                 return {
#                     "status": "info",
#                     "message": "No associated schedule found"
#                 }

#             # Map Twilio call status to our schedule status
#             schedule_status = self._map_call_status_to_schedule_status(call_status)
            
#             # Prepare update data
#             update_data = {
#                 "status": schedule_status,
#                 "last_updated": datetime.utcnow()
#             }
            
#             if duration is not None:
#                 update_data["duration"] = duration

#             # Update the schedule
#             result = self.db.call_schedules.update_one(
#                 {"id": schedule["id"]},
#                 {"$set": update_data}
#             )

#             if result.matched_count > 0:
#                 logger.info(f"Updated schedule {schedule['id']} status to {schedule_status}")
#                 return {
#                     "status": "success",
#                     "message": f"Schedule status updated to {schedule_status}",
#                     "schedule_id": schedule["id"]
#                 }
#             else:
#                 logger.error(f"Failed to update schedule {schedule['id']}")
#                 return {
#                     "status": "error",
#                     "message": "Failed to update schedule"
#                 }

#         except Exception as e:
#             logger.error(f"Error updating schedule status: {e}")
#             return {
#                 "status": "error",
#                 "message": f"Failed to update schedule status: {str(e)}"
#             }

#     def _map_call_status_to_schedule_status(self, twilio_status: str) -> str:
#         """Map Twilio call status to our internal schedule status"""
#         status_mapping = {
#             "completed": CallStatus.COMPLETED.value,
#             "failed": CallStatus.FAILED.value,
#             "busy": CallStatus.FAILED.value,
#             "no-answer": CallStatus.FAILED.value,
#             "canceled": CallStatus.CANCELLED.value,
#             "queued": CallStatus.PENDING.value,
#             "initiated": CallStatus.PENDING.value,
#             "ringing": CallStatus.PENDING.value,
#             "in-progress": CallStatus.PENDING.value
#         }
        
#         return status_mapping.get(twilio_status.lower(), CallStatus.FAILED.value)

#     async def create_call_log_from_webhook(self, call_data: Dict[str, Any]) -> Dict[str, Any]:
#         """
#         Create a call log entry from webhook data if it doesn't exist
#         This is useful for incoming calls or calls not tracked initially
#         """
#         try:
#             call_sid = call_data.get("CallSid")
            
#             # Check if call log already exists
#             existing_log = self.db.call_logs.find_one({"call_id": call_sid})
#             if existing_log:
#                 logger.info(f"Call log already exists for {call_sid}")
#                 return {
#                     "status": "info",
#                     "message": "Call log already exists"
#                 }

#             # Extract call information
#             from_number = call_data.get("From", "")
#             to_number = call_data.get("To", "")
#             call_status = call_data.get("CallStatus", "unknown")
#             direction = call_data.get("Direction", "outbound")
            
#             # Determine call type based on direction
#             call_type = CallType.INCOMING.value if direction == "inbound" else CallType.OUTGOING.value

#             # Create basic call log entry
#             # Note: For webhook-created logs, we may not have all user profile info
#             call_log = CallLog(
#                 id=str(uuid4()),
#                 created_by="webhook",  # Default for webhook-created logs
#                 user_profile_id="unknown",  # Will need to be updated later if possible
#                 agent_instance_id="default",
#                 call_id=call_sid,
#                 status=CallStatus(call_status) if call_status in [s.value for s in CallStatus] else CallStatus.PENDING,
#                 call_type=CallType(call_type),
#                 phone=from_number if direction == "inbound" else to_number,
#                 timestamp=datetime.utcnow(),
#                 notes=f"Created from webhook - Direction: {direction}"
#             )

#             # Insert into database
#             result = self.db.call_logs.insert_one(call_log.dict())
            
#             logger.info(f"Created call log from webhook for {call_sid}")
            
#             return {
#                 "status": "success",
#                 "message": "Call log created from webhook",
#                 "call_log_id": call_log.id
#             }

#         except Exception as e:
#             logger.error(f"Error creating call log from webhook: {e}")
#             return {
#                 "status": "error",
#                 "message": f"Failed to create call log from webhook: {str(e)}"
#             }
