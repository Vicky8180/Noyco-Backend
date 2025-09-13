"""
Twilio controller for handling outbound calls - FIXED VERSION
"""

import asyncio
from datetime import datetime
import uuid
import logging
from typing import Dict, List, Optional, Any
from twilio.rest import Client
from twilio.base.exceptions import TwilioException
from twilio.twiml.voice_response import VoiceResponse
from enum import Enum

from ..config import settings
from ..schema import (
    OutboundCallRequest, BatchOutboundCallRequest,
    OutboundCallResponse, BatchOutboundCallResponse,
    CallRecord, CallStatus
)

logger = logging.getLogger(__name__)
# Set up more detailed logging for debugging
logging.basicConfig(level=logging.INFO)


class OutboundController:
    """Controller for managing outbound Twilio voice calls"""

    def __init__(self):
        """Initialize Twilio client"""
        try:
            self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            logger.debug("Twilio client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Twilio client: {e}", exc_info=True)
            raise

        self.active_batches: Dict[str, Dict] = {}
        self.call_records: Dict[str, CallRecord] = {}
        self.default_callback_url = f"{settings.TWILIO_BASE_WEBHOOK_URL}/phone/voice"
        logger.debug(f"Default callback URL set to: {self.default_callback_url}")

    async def make_call(self, request: OutboundCallRequest) -> OutboundCallResponse:
        """Make a single outbound call"""
        try:
            # Ensure we have required fields
            print(request)
            
            # Validate that user_profile_id is provided
            if not request.user_profile_id:
                logger.error("User profile ID is required for all calls")
                return OutboundCallResponse(
                    call_sid="",
                    status="error",
                    message="User profile ID is required for all calls"
                )
            
            # created_by can be optional - will be set based on the calling context
            query_params = {
                "user_profile_id": request.user_profile_id,
                "created_by": request.created_by,  # User ID who created the call
                "agent_instance_id": request.agent_instance_id,
                "conversation_id": f"conversation_{uuid.uuid4()}"
            }
            
            print(f"Query params: {query_params}")
                
            # Use provided number or default
            from_number = request.from_number or settings.TWILIO_PHONE_NUMBER
            logger.info(f"Making call from {from_number} to {request.to_number}")

            # For outbound calls, don't use TwiML directly - use the callback URL
            # This ensures the call flow goes through the same voice endpoint as incoming calls
            # callback_url = request.callback_url or self.default_callback_url
            # logger.info(f"Using callback URL: {callback_url}")
            
            query_string = "&".join(f"{k}={v}" for k, v in query_params.items() if v)

# Add query string to default callback URL
            callback_url = (request.callback_url or self.default_callback_url)
            if query_string:
                callback_url += f"?{query_string}"

            # Make the call - let the voice endpoint handle the TwiML generation
            call = self.client.calls.create(
               to = f"+91{request.to_number}",
                from_=from_number,
                url=callback_url,
                method="POST",
                timeout=request.timeout,
                record=request.record,
                status_callback=f"{settings.TWILIO_BASE_WEBHOOK_URL}/phone/status",
                status_callback_event=["initiated", "ringing", "answered", "completed"],
                status_callback_method="POST"
            )
            logger.info(f"Call created: {call.sid}, Status: {call.status}")

            # Create call record
            await self._create_call_record(
                call_sid=call.sid,
                account_sid=call.account_sid,
                from_number=from_number,
                to_number=request.to_number,
                status=call.status,
                direction="outbound-api",
                user_profile_id=request.user_profile_id,
                created_by=request.created_by,
                agent_instance_id=request.agent_instance_id
            )

            logger.info(f"Outbound call created: {call.sid} to {request.to_number}")

            return OutboundCallResponse(
                call_sid=call.sid,
                status="initiated",
                message=f"Call to {request.to_number} initiated",
                details={
                    "from": from_number,
                    "to": request.to_number,
                    "status": call.status
                }
            )

        except TwilioException as e:
            logger.error(f"Twilio error making outbound call: {str(e)}", exc_info=True)
            return OutboundCallResponse(
                call_sid="",
                status="error",
                message=f"Twilio error: {str(e)}",
                details={"error": str(e)}
            )

        except Exception as e:
            logger.error(f"Unexpected error making outbound call: {str(e)}", exc_info=True)
            return OutboundCallResponse(
                call_sid="",
                status="error",
                message=f"Error: {str(e)}",
                details={"error": str(e)}
            )


    async def get_call_status(self, call_sid: str) -> Optional[Dict[str, Any]]:
        """Get current status of a call from Twilio"""
        try:
            call = self.client.calls(call_sid).fetch()

            return {
                "call_sid": call.sid,
                "status": call.status,
                "direction": call.direction,
                "from": call.from_,
                "to": call.to,
                "duration": call.duration,
                "start_time": call.start_time,
                "end_time": call.end_time,
                "price": call.price,
                "price_unit": call.price_unit
            }

        except TwilioException as e:
            logger.error(f"Twilio error fetching call status: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error fetching call status: {str(e)}")
            return None


    async def cancel_call(self, call_sid: str) -> bool:
        """Cancel an active call"""
        try:
            call = self.client.calls(call_sid).update(status="canceled")
            logger.info(f"Call {call_sid} canceled")

            # Update local call record
            if call_sid in self.call_records:
                self.call_records[call_sid].status = CallStatus.FAILED
                self.call_records[call_sid].end_time = datetime.utcnow()

            return True
        except Exception as e:
            logger.error(f"Error canceling call {call_sid}: {str(e)}")
            return False



    async def _create_call_record(self, call_sid: str, account_sid: str, from_number: str,
                                 to_number: str, status: str, direction: str, 
                                 user_profile_id: Optional[str] = None, created_by: Optional[str] = None, 
                                 agent_instance_id: Optional[str] = None) -> CallRecord:
        """Create a call record for tracking"""
        call_record = CallRecord(
            call_sid=call_sid,
            account_sid=account_sid,
            from_number=from_number,
            to_number=to_number,
            status=CallStatus(status),
            direction=direction,
            user_profile_id=user_profile_id,
            created_by=created_by,  # User ID who created the call
            agent_instance_id=agent_instance_id,
            start_time=datetime.utcnow()
        )

        # Store call record
        self.call_records[call_sid] = call_record
        logger.info(f"Created call record for outbound call {call_sid}")

        return call_record




