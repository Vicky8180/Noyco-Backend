


# # schema.py - Updated with new scheduling schemas

# from pydantic import BaseModel, Field, validator
# from typing import Optional, List, Literal, Dict, Any
# from enum import Enum
# from datetime import datetime


# # ---------------- ENUMS ----------------

# class CallStatus(str, Enum):
#     PENDING = "pending"
#     COMPLETED = "completed"
#     FAILED = "failed"
#     CANCELLED = "cancelled"


# class RepeatType(str, Enum):
#     ONCE = "once"
#     DAILY = "daily"
#     WEEKLY = "weekly"
#     MONTHLY = "monthly"
#     CUSTOM = "custom"


# class CallType(str, Enum):
#     INCOMING = "incoming"
#     OUTGOING = "outgoing"
#     LIVEKIT = "livekit"


# class ScheduleAction(str, Enum):
#     ACTIVE = "active"
#     PAUSE = "pause"
#     RESUME = "resume"
#     CANCEL = "cancel"
#     DELETE = "delete"


# # ---------------- OUTBOUND CALL SCHEMAS ----------------


# # ---------------- OUTBOUND CALL SCHEMAS ----------------

# class OutboundCallRequest(BaseModel):
#     """Schema for outbound call request"""
#     to_number: str = Field(..., description="Destination phone number")
#     from_number: Optional[str] = Field(None, description="Source phone number (will use default if not specified)")
#     user_profile_id: Optional[str] = Field(None, description="Profile ID for whom the call is created (e.g., mom profile, dad profile)")
#     created_by: Optional[str] = Field(None, description="User ID who is creating/initiating this call")
#     agent_instance_id: Optional[str] = Field(None, description="Agent instance ID for tracking")
#     message: Optional[str] = Field(None, description="Initial message to be spoken")
#     callback_url: Optional[str] = Field(None, description="Custom callback URL")
#     timeout: Optional[int] = Field(60, description="Call timeout in seconds")
#     record: bool = Field(False, description="Whether to record the call")


# class BatchOutboundCallRequest(BaseModel):
#     """Schema for batch outbound calls"""
#     calls: List[OutboundCallRequest] = Field(..., min_items=1, max_items=100, description="List of calls to make")
#     sequential: bool = Field(False, description="If true, calls are made one after another")
#     delay_between_calls: Optional[int] = Field(5, description="Delay between sequential calls in seconds")


# class OutboundCallResponse(BaseModel):
#     """Schema for outbound call response"""
#     call_sid: str = Field(..., description="Twilio call SID")
#     status: str = Field(..., description="Call status")
#     message: str = Field(..., description="Status message")
#     details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


# class BatchOutboundCallResponse(BaseModel):
#     """Schema for batch outbound call response"""
#     success_count: int = Field(..., description="Number of successful calls")
#     failure_count: int = Field(..., description="Number of failed calls")
#     results: List[OutboundCallResponse] = Field(..., description="Individual call results")
#     batch_id: str = Field(..., description="Unique ID for this batch")


# # ---------------- SCHEDULING SCHEMAS ----------------

# class CallSchedule(BaseModel):
#     id: str
#     created_by: str  # assistant ID who created the schedule
#     user_profile_id: str  # unified user profile ID (replaces patient_id, hospital_id, individual_id)
#     agent_instance_id: str  # specific agent instance to handle the call
#     attended_by: Optional[str] = None  # assistant ID
#     schedule_time: datetime
#     repeat_type: RepeatType = RepeatType.ONCE
#     repeat_interval: Optional[int] = None  # only for CUSTOM
#     repeat_unit: Optional[Literal['minutes','hours','days', 'weeks', 'months']] = None  # unit for repeat interval
#     repeat_days: Optional[List[str]] = None  # e.g., ['monday', 'friday']
#     status: CallStatus = CallStatus.PENDING
#     duration: Optional[int] = None  # seconds
#     condition: Optional[str] = None  # e.g., "age > 60 AND bp"
#     call_id: Optional[str] = None  # twilio/livekit session
#     phone: str
#     notes: Optional[str] = None
#     is_deleted: bool = False
#     schedule_action: ScheduleAction = ScheduleAction.ACTIVE

#     @validator('repeat_interval')
#     def validate_repeat_interval(cls, v, values):
#         if values.get("repeat_type") == RepeatType.CUSTOM and not v:
#             raise ValueError("repeat_interval is required for custom repeat type")
#         return v
        
#     @validator('repeat_unit')
#     def validate_repeat_unit(cls, v, values):
#         if values.get("repeat_type") == RepeatType.CUSTOM and not v:
#             raise ValueError("repeat_unit is required for custom repeat type")
#         return v


# class ActiveSchedule(BaseModel):
#     id: str
#     created_by: str
#     call_schedule_id: str
#     user_profile_id: str
#     agent_instance_id: str
#     next_run_time: datetime
#     retry_count: int = 0
#     is_paused: bool = False
#     schedule_action: ScheduleAction = ScheduleAction.ACTIVE
#     last_attempt_time: Optional[datetime] = None
#     last_status: Optional[CallStatus] = None


# class CallLog(BaseModel):
#     id: str
#     created_by: str  # assistant ID who created/initiated the call
#     user_profile_id: str  # unified user profile ID
#     agent_instance_id: str  # specific agent instance that handled the call
#     assistant_id: Optional[str] = None  # fallback/additional assistant info
#     status: CallStatus
#     call_type: CallType
#     phone: str
#     call_id: Optional[str] = None  # Twilio call SID
#     conversation_id: Optional[str] = None
#     duration: Optional[int] = None  # Call duration in seconds
#     start_time: Optional[datetime] = None  # Call start time
#     end_time: Optional[datetime] = None  # Call end time
#     notes: Optional[str] = None
#     is_ai_handled: bool = True
#     fallback_to_human: bool = False
#     timestamp: datetime = Field(default_factory=datetime.utcnow)


# # ---------------- REQUEST/RESPONSE SCHEMAS ----------------

# class CreateScheduleRequest(BaseModel):
#     """Schema for creating a new call schedule"""
#     created_by: str = Field(..., description="Assistant ID creating the schedule")
#     user_profile_id: str = Field(..., description="User profile ID")
#     agent_instance_id: str = Field(..., description="Agent instance ID to handle the call")
#     schedule_time: datetime = Field(..., description="When to schedule the call")
#     repeat_type: RepeatType = Field(RepeatType.ONCE, description="Type of repeat schedule")
#     repeat_interval: Optional[int] = Field(None, description="Interval for custom repeat")
#     repeat_unit: Optional[Literal['minutes','hours','days', 'weeks', 'months']] = Field(None, description="Unit for repeat interval")
#     repeat_days: Optional[List[str]] = Field(None, description="Days for weekly repeat")
#     phone: str = Field(..., description="Phone number to call")
#     condition: Optional[str] = Field(None, description="Condition for scheduling")
#     notes: Optional[str] = Field(None, description="Additional notes")
        
#     @validator('repeat_interval')
#     def validate_repeat_interval_with_type(cls, v, values):
#         repeat_type = values.get('repeat_type')
#         if repeat_type == RepeatType.CUSTOM and not v:
#             raise ValueError("repeat_interval is required for custom repeat type")
#         return v
        
#     @validator('repeat_unit')
#     def validate_repeat_unit_with_type(cls, v, values):
#         repeat_type = values.get('repeat_type')
#         if repeat_type == RepeatType.CUSTOM and not v:
#             raise ValueError("repeat_unit is required for custom repeat type")
#         return v


# class UpdateScheduleRequest(BaseModel):
#     """Schema for updating a call schedule"""
#     schedule_time: Optional[datetime] = None
#     repeat_type: Optional[RepeatType] = None
#     repeat_interval: Optional[int] = None
#     repeat_unit: Optional[Literal['minutes','hours','days', 'weeks', 'months']] = None
#     repeat_days: Optional[List[str]] = None
#     condition: Optional[str] = None
#     notes: Optional[str] = None
#     schedule_action: Optional[ScheduleAction] = None


# class ScheduleResponse(BaseModel):
#     """Schema for schedule response"""
#     id: str
#     status: str
#     message: str
#     schedule: Optional[CallSchedule] = None


# class ScheduleStatsResponse(BaseModel):
#     """Schema for schedule statistics"""
#     total_scheduled: int
#     pending: int
#     completed: int
#     failed: int
#     cancelled: int
#     active_schedules: int
#     paused_schedules: int


# class ScheduleListResponse(BaseModel):
#     """Schema for schedule list response"""
#     schedules: List[CallSchedule]
#     total: int
#     page: int
#     per_page: int


# class CallStatsResponse(BaseModel):
#     """Schema for call statistics response"""
#     total_calls: int
#     completed_calls: int
#     failed_calls: int
#     pending_calls: int
#     cancelled_calls: int
#     calls_by_time: Dict[str, int]  # hourly distribution
#     calls_by_status: Dict[str, int]

