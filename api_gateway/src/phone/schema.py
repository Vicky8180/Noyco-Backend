# from pydantic import BaseModel, Field
# from typing import List, Dict, Optional, Literal, Any
# from datetime import datetime
# from enum import Enum

# class HospitalStatus(str, Enum):
#     ACTIVE = "active"
#     INACTIVE = "inactive"
#     SUSPENDED = "suspended"

# class PlanType(str, Enum):
#     LITE = "lite"
#     PRO = "pro"

# # Removed CreatedBy enum - created_by is now a string ID

# class TwilioNumberCapabilities(BaseModel):
#     voice: bool = False
#     sms: bool = False
#     mms: bool = False

# class TwilioNumberConfig(BaseModel):
#     phone_number: Optional[str] = None
#     phone_number_sid: Optional[str] = None
#     subaccount_sid: Optional[str] = None
#     webhook_urls: Optional[Dict[str, str]] = None
#     capabilities: Optional[TwilioNumberCapabilities] = None
#     area_code: Optional[str] = None
#     country_code: str = "US"
#     created_at: Optional[datetime] = None
#     status: str = "active"

# class Hospital(BaseModel):
#     id: str
#     hospital_name: str
#     hospital_unique_identity: str
#     email: str
#     password_hash: str
#     phone: str
#     website_link: Optional[str] = None
#     plan: Optional[PlanType] = None
#     status: HospitalStatus = HospitalStatus.ACTIVE
#     created_at: datetime
#     updated_at: datetime
#     # New field for Twilio configuration
#     twilio_config: Optional[TwilioNumberConfig] = None

# class GenerateNumberRequest(BaseModel):
#     user_profile_id: str
#     area_code: Optional[str] = None
#     country_code: str = "US"

# class GenerateNumberResponse(BaseModel):
#     status: str
#     message: str
#     user_profile_config: Dict[str, Any]
#     phone_number: str
#     webhook_url: str









# class CallStatus(str, Enum):
#     """Call status enumeration"""
#     INITIATED = "initiated"
#     RINGING = "ringing"
#     IN_PROGRESS = "in-progress"
#     COMPLETED = "completed"
#     FAILED = "failed"
#     BUSY = "busy"
#     NO_ANSWER = "no-answer"
#     queued      = "queued"        # ← add this
#     initiated   = "initiated"
#     ringing     = "ringing"
#     in_progress = "in-progress"
#     completed   = "completed"
#     failed      = "failed"
#     busy        = "busy"
#     no_answer   = "no-answer"
#     canceled    = "canceled"
#     timeout     = "timeout"

# class TwilioVoiceRequest(BaseModel):
#     """Twilio voice webhook request schema"""
#     CallSid: str = Field(..., description="Unique identifier for the call")
#     AccountSid: str = Field(..., description="Twilio Account SID")
#     From: str = Field(..., description="Phone number that initiated the call")
#     To: str = Field(..., description="Phone number that received the call")
#     CallStatus: str = Field(..., description="Status of the call")
#     Direction: str = Field(..., description="Direction of the call")
#     ForwardedFrom: Optional[str] = Field(None, description="Forwarded from number")
#     CallerName: Optional[str] = Field(None, description="Caller name if available")


# class CallRecord(BaseModel):
#     """Call record schema with new unified fields"""
#     call_sid: str
#     account_sid: str
#     from_number: str
#     to_number: str
#     status: CallStatus
#     direction: str
#     user_profile_id: Optional[str] = Field(None, description="Profile ID for whom the call is created (e.g., mom profile, dad profile)")
#     created_by: Optional[str] = Field(None, description="User ID who created/initiated this call")
#     agent_instance_id: Optional[str] = None
#     start_time: datetime
#     end_time: Optional[datetime] = None
#     duration: Optional[int] = None
#     forwarded_from: Optional[str] = None
#     caller_name: Optional[str] = None


# class ChatbotRequest(BaseModel):
#     """Chatbot request schema"""
#     userText: str = Field(..., min_length=1, max_length=1000, description="User input text")
#     context: Optional[Dict[str, Any]] = Field(None, description="Optional context data")


# class ChatbotResponse(BaseModel):
#     """Chatbot response schema"""
#     response: str = Field(..., description="Chatbot response text")
#     timestamp: datetime = Field(default_factory=datetime.utcnow)


# class AudioData(BaseModel):
#     """Audio data schema"""
#     audio_data: bytes = Field(..., description="Raw audio data")
#     sample_rate: int = Field(8000, description="Audio sample rate")
#     channels: int = Field(1, description="Number of audio channels")
#     encoding: str = Field("mulaw", description="Audio encoding format")


# class TranscriptionResult(BaseModel):
#     """Speech-to-text transcription result"""
#     text: str = Field(..., description="Transcribed text")
#     confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
#     is_final: bool = Field(False, description="Whether this is the final transcription")


# class TTSRequest(BaseModel):
#     """Text-to-speech request schema"""
#     text: str = Field(..., min_length=1, max_length=5000, description="Text to convert to speech")
#     voice: Optional[str] = Field("aura-asteria-en", description="Voice model to use")
#     speed: Optional[float] = Field(1.0, ge=0.5, le=2.0, description="Speech speed")







# # ...existing code...

# class OutboundCallRequest(BaseModel):
#     """Schema for outbound call request with new unified fields"""
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

















