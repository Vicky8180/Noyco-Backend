

# ============================================================================
# controllers/tracking.py - Tracking Controller
# ============================================================================

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import uuid4
import logging

from api_gateway.database.db import get_database
from ..schema import CallLog, CallStatus, CallType, CallStatsResponse

logger = logging.getLogger(__name__)


class TrackingController:
    def __init__(self):
        self.db = get_database()

    async def log_call(self, user_profile_id: str, phone: str,
                      call_type: str, status: str, created_by: str,
                      call_id: Optional[str] = None, agent_instance_id: Optional[str] = None,
                      assistant_id: Optional[str] = None, conversation_id: Optional[str] = None, 
                      notes: Optional[str] = None, duration: Optional[int] = None, 
                      start_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Log a call to the database"""
        try:
            # Debug log input parameters
            logger.info(f"log_call called with params: user_profile_id={user_profile_id}, created_by={created_by}, phone={phone}, call_id={call_id}")
            
            call_log = CallLog(
                id=str(uuid4()),
                created_by=created_by,
                user_profile_id=user_profile_id,
                agent_instance_id=agent_instance_id or "default",
                assistant_id=assistant_id,
                status=CallStatus(status),
                call_type=CallType(call_type),
                phone=phone,
                call_id=call_id,
                conversation_id=conversation_id,
                duration=duration,
                start_time=start_time,
                end_time=end_time,
                notes=notes,
                timestamp=datetime.utcnow()
            )

            # Convert to dict for database insertion
            call_data = call_log.dict()

            # Debug log what's being inserted
            logger.info(f"Inserting call log with data: user_profile_id={call_data.get('user_profile_id')}, created_by={call_data.get('created_by')}, call_id={call_data.get('call_id')}, conversation_id={call_data.get('conversation_id')}")
            
            # Remove await for insert_one - synchronous operation
            result = self.db.call_logs.insert_one(call_data)
            
            logger.info(f"Call log inserted with ID: {result.inserted_id}")

            return {
                "status": "success",
                "message": "Call logged successfully",
                "call_log_id": call_log.id
            }

        except Exception as e:
            logger.error(f"Error logging call: {e}")
            return {
                "status": "error",
                "message": f"Failed to log call: {str(e)}"
            }

    async def get_call_stats(self, user_profile_id: Optional[str] = None,
                           created_by: Optional[str] = None,
                           start_date: Optional[datetime] = None,
                           end_date: Optional[datetime] = None) -> CallStatsResponse:
        """Get call statistics"""
        try:
            # Build filter query
            filter_query = {}
            
            # Filter by user profile or creator
            if user_profile_id:
                filter_query["user_profile_id"] = user_profile_id
            if created_by:
                filter_query["created_by"] = created_by

            if start_date or end_date:
                time_filter = {}
                if start_date:
                    time_filter["$gte"] = start_date
                if end_date:
                    time_filter["$lte"] = end_date
                filter_query["timestamp"] = time_filter

            # Get total counts by status
            pipeline = [
                {"$match": filter_query},
                {"$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }}
            ]

            # Use list() instead of to_list() for aggregate operations
            status_counts = {doc["_id"]: doc["count"] for doc in list(self.db.call_logs.aggregate(pipeline))}

            # Get hourly distribution
            hourly_pipeline = [
                {"$match": filter_query},
                {"$group": {
                    "_id": {"$hour": "$timestamp"},
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]

            # Use list() instead of to_list() for aggregate operations
            hourly_data = list(self.db.call_logs.aggregate(hourly_pipeline))
            calls_by_time = {f"{doc['_id']}:00": doc["count"] for doc in hourly_data}

            total_calls = sum(status_counts.values())

            return CallStatsResponse(
                total_calls=total_calls,
                completed_calls=status_counts.get(CallStatus.COMPLETED.value, 0),
                failed_calls=status_counts.get(CallStatus.FAILED.value, 0),
                pending_calls=status_counts.get(CallStatus.PENDING.value, 0),
                cancelled_calls=status_counts.get(CallStatus.CANCELLED.value, 0),
                calls_by_time=calls_by_time,
                calls_by_status=status_counts
            )

        except Exception as e:
            logger.error(f"Error getting call stats: {e}")
            return CallStatsResponse(
                total_calls=0, completed_calls=0, failed_calls=0,
                pending_calls=0, cancelled_calls=0,
                calls_by_time={}, calls_by_status={}
            )

    async def get_call_history(self, user_profile_id: Optional[str] = None,
                             created_by: Optional[str] = None,
                             call_type: Optional[str] = None,
                             page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        """Get call history with pagination"""
        try:
            filter_query = {}
            
            if user_profile_id:
                filter_query["user_profile_id"] = user_profile_id
            if created_by:
                filter_query["created_by"] = created_by
            if call_type:
                filter_query["call_type"] = call_type

            # Get total count - remove await for count_documents
            total = self.db.call_logs.count_documents(filter_query)

            # Get call history with pagination - use list() instead of to_list()
            skip = (page - 1) * per_page
            call_logs = list(self.db.call_logs.find(filter_query).sort("timestamp", -1).skip(skip).limit(per_page))

            return {
                "status": "success",
                "call_logs": call_logs,
                "total": total,
                "page": page,
                "per_page": per_page
            }

        except Exception as e:
            logger.error(f"Error getting call history: {e}")
            return {
                "status": "error",
                "message": f"Failed to get call history: {str(e)}",
                "call_logs": [],
                "total": 0,
                "page": page,
                "per_page": per_page
            }

    async def update_call_status(self, call_id: str, status: str, notes: Optional[str] = None) -> Dict[str, Any]:
        """Update call status"""
        try:
            update_data = {"status": status}
            if notes:
                update_data["notes"] = notes

            # Remove await for update_one - synchronous operation
            result = self.db.call_logs.update_one(
                {"call_id": call_id},
                {"$set": update_data}
            )

            if result.matched_count > 0:
                return {
                    "status": "success",
                    "message": "Call status updated successfully"
                }
            else:
                return {
                    "status": "error",
                    "message": "Call not found"
                }

        except Exception as e:
            logger.error(f"Error updating call status: {e}")
            return {
                "status": "error",
                "message": f"Failed to update call status: {str(e)}"
            }

    async def update_call_details(self, call_id: str, status: Optional[str] = None,
                                 duration: Optional[int] = None, conversation_id: Optional[str] = None,
                                 start_time: Optional[datetime] = None, end_time: Optional[datetime] = None,
                                 notes: Optional[str] = None) -> Dict[str, Any]:
        """Update call details including duration, conversation_id, and timing"""
        try:
            update_data = {}
            
            if status:
                update_data["status"] = status
            if duration is not None:
                update_data["duration"] = duration
            if conversation_id:
                update_data["conversation_id"] = conversation_id
            if start_time:
                update_data["start_time"] = start_time
            if end_time:
                update_data["end_time"] = end_time
            if notes:
                update_data["notes"] = notes

            if not update_data:
                return {
                    "status": "error",
                    "message": "No data to update"
                }

            logger.info(f"Updating call {call_id} with data: {update_data}")

            # Remove await for update_one - synchronous operation
            result = self.db.call_logs.update_one(
                {"call_id": call_id},
                {"$set": update_data}
            )

            if result.matched_count > 0:
                logger.info(f"Successfully updated call {call_id}")
                return {
                    "status": "success",
                    "message": "Call details updated successfully",
                    "updated_fields": list(update_data.keys())
                }
            else:
                logger.warning(f"Call {call_id} not found in call_logs")
                return {
                    "status": "error",
                    "message": "Call not found"
                }

        except Exception as e:
            logger.error(f"Error updating call details: {e}")
            return {
                "status": "error",
                "message": f"Failed to update call details: {str(e)}"
            }
