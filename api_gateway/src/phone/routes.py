

from fastapi import APIRouter, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, StreamingResponse
from typing import Optional, Dict, AsyncGenerator
from twilio.twiml.voice_response import VoiceResponse
import json
import base64
import logging

from .controllers.incoming import IncomingController
from .controllers.outbound import OutboundController
from .schema import (
    GenerateNumberRequest, GenerateNumberResponse, TwilioVoiceRequest,
    CallRecord, ChatbotRequest, ChatbotResponse,
    OutboundCallRequest, BatchOutboundCallRequest,
    OutboundCallResponse, BatchOutboundCallResponse
)
from .services.stt_service import STTService
from .services.tts_service import TTSService
from .services.chatbot_service import ChatbotService





# Initialize the outbound controller
outbound_controller = OutboundController()

logger = logging.getLogger(__name__)

phone_router = APIRouter(prefix="/phone", tags=["Phone Numbers"])

incoming_controller = IncomingController()
stt_service = STTService()
tts_service = TTSService()
chatbot_service = ChatbotService()

# Incoming call - moved logic to controller
@phone_router.post("/voice")
async def handle_voice_call(request: Request):
    return await incoming_controller.handle_voice_call(request)

# Single outbound call
@phone_router.post("/call", response_model=OutboundCallResponse, summary="Make an outbound call")
async def make_outbound_call(request: OutboundCallRequest):
    print(request)

    return await outbound_controller.make_call(request)

@phone_router.post("/gather-response")
async def handle_gather_response(request: Request):
    return await incoming_controller.handle_gather_response(request)

# Legacy websocket endpoint - kept for compatibility but no longer used in default mode
@phone_router.websocket("/ws/{call_sid}")
async def websocket_endpoint(websocket: WebSocket, call_sid: str):
    await incoming_controller.handle_media_stream(websocket, call_sid, stt_service, tts_service, chatbot_service)

# Call status - moved logic to controller
@phone_router.post("/status")
async def handle_call_status(request: Request):
    return await incoming_controller.handle_call_status(request)

@phone_router.get("/connect")
async def handle_connect_endpoint(request: Request):
    return await incoming_controller.handle_connect(request)


# Chatbot routes - moved logic to service
@phone_router.post("/chatbot")
async def chatbot_endpoint(request: ChatbotRequest):
    return await chatbot_service.handle_streaming_chatbot_request(request)



# Get call status
@phone_router.get("/call/{call_sid}", summary="Get status of a call")
async def get_call_status(call_sid: str):
    """Get current status of a specific call by SID"""
    status = await outbound_controller.get_call_status(call_sid)
    if status:
        return status
    return {"status": "error", "message": "Call not found"}


# Cancel call
@phone_router.post("/call/{call_sid}/cancel", summary="Cancel an active call")
async def cancel_call(call_sid: str):
    """Cancel an in-progress call"""
    success = await outbound_controller.cancel_call(call_sid)
    if success:
        return {"status": "success", "message": f"Call {call_sid} canceled"}
    return {"status": "error", "message": "Failed to cancel call"}



# Test endpoint for user verification
@phone_router.post("/test-verification", summary="Test user verification by phone number")
async def test_user_verification(request: dict):
    """Test endpoint to verify user by phone number"""
    from .services.userVerification import UserVerificationService
    
    verification_service = UserVerificationService()
    phone_number = request.get("phone_number", "")
    
    if not phone_number:
        return {"error": "phone_number is required"}
    
    result = await verification_service.verify_user_by_phone(phone_number)
    return result



