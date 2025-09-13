import logging
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from twilio.rest import Client
from twilio.base.exceptions import TwilioException

from api_gateway.database.db import get_database
from ..schema import Hospital, TwilioNumberConfig, TwilioNumberCapabilities
from ..config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PhoneGeneratorController:
    """Handles logic for hospital Twilio number generation"""

    def __init__(self):
        self.db = get_database()
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    def _generate_friendly_name(self, hospital_name: str, hospital_id: str) -> str:
        """Generate a friendly name for the subaccount"""
        clean_name = ''.join(c for c in hospital_name if c.isalnum() or c.isspace()).title()
        return f"AI Assistant - {clean_name} ({hospital_id})"

    async def _create_subaccount(self, hospital_name: str, hospital_id: str) -> Dict[str, Any]:
        """Create a Twilio subaccount for a hospital"""
        try:
            friendly_name = self._generate_friendly_name(hospital_name, hospital_id)

            # Create subaccount
            subaccount = self.client.api.accounts.create(
                friendly_name=friendly_name
            )

            logger.info(f"✅ Created subaccount for hospital {hospital_id}: {subaccount.sid}")

            return {
                "subaccount_sid": subaccount.sid,
                "friendly_name": friendly_name,
                "status": subaccount.status,
                "date_created": subaccount.date_created.isoformat() if subaccount.date_created else None
            }

        except TwilioException as e:
            logger.error(f"❌ Twilio error creating subaccount for {hospital_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Twilio error: {str(e)}"
            )

    async def _purchase_phone_number(self, subaccount_sid: str, hospital_id: str,
                                   area_code: Optional[str] = None, country_code: str = "US") -> Dict[str, Any]:
        """Purchase a phone number for the hospital's subaccount"""
        try:
            # Create client for the subaccount
            sub_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, subaccount_sid)

            # Search for available phone numbers
            search_params = {
                "limit": 20,
                "voice_enabled": True,
                "sms_enabled": True
            }

            if area_code:
                search_params["area_code"] = area_code

            logger.info(f"🔍 Searching for available numbers with params: {search_params}")

            # Search for numbers
            if country_code == "US":
                available_numbers = sub_client.available_phone_numbers("US").local.list(**search_params)
            else:
                available_numbers = sub_client.available_phone_numbers(country_code).local.list(**search_params)

            if not available_numbers:
                # Try without area code if no numbers found
                if area_code:
                    logger.warning(f"⚠️ No numbers found for area code {area_code}, trying without area code")
                    search_params.pop("area_code", None)
                    available_numbers = sub_client.available_phone_numbers("US").local.list(**search_params)

                if not available_numbers:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"No available phone numbers found for country {country_code}"
                    )

            # Purchase the first available number
            selected_number = available_numbers[0]
            logger.info(f"📞 Selected number: {selected_number.phone_number}")

            # Generate webhook URLs
            webhook_urls = settings.get_twilio_webhook_urls(hospital_id)

            # Purchase the number with webhook configuration
            purchased_number = sub_client.incoming_phone_numbers.create(
                phone_number=selected_number.phone_number,
                voice_url=webhook_urls["voice_webhook"],
                voice_method="POST",
                status_callback=webhook_urls["status_webhook"],
                status_callback_method="POST"
            )

            logger.info(f"✅ Successfully purchased number for hospital {hospital_id}: {purchased_number.phone_number}")

            return {
                "phone_number": purchased_number.phone_number,
                "phone_number_sid": purchased_number.sid,
                "webhook_urls": webhook_urls,
                "capabilities": TwilioNumberCapabilities(
                    voice=getattr(purchased_number.capabilities, 'voice', False),
                    sms=getattr(purchased_number.capabilities, 'sms', False),
                    mms=getattr(purchased_number.capabilities, 'mms', False)
                )
            }

        except TwilioException as e:
            logger.error(f"❌ Twilio error purchasing number for {hospital_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Twilio error: {str(e)}"
            )

    async def generate_hospital_number(self, hospital_id: str, area_code: Optional[str] = None,
                                     country_code: str = "US") -> Dict[str, Any]:
        """Generate a complete Twilio setup for a hospital"""
        try:
            # Get hospital from database
            hospital = self.db.hospitals.find_one({"id": hospital_id})
            if not hospital:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Hospital with ID {hospital_id} not found"
                )

            # Check if hospital already has Twilio configuration
            if hospital.get("twilio_config") and hospital["twilio_config"].get("phone_number"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Hospital {hospital_id} already has a phone number configured"
                )

            # Step 1: Create subaccount
            logger.info(f"🏥 Starting setup for hospital {hospital_id}")
            subaccount_info = await self._create_subaccount(hospital["hospital_name"], hospital_id)

            # Step 2: Purchase phone number
            logger.info(f"📞 Purchasing phone number for hospital {hospital_id}")
            number_info = await self._purchase_phone_number(
                subaccount_info["subaccount_sid"],
                hospital_id,
                area_code,
                country_code
            )

            # Step 3: Create Twilio configuration
            twilio_config_data = TwilioNumberConfig(
                phone_number=number_info["phone_number"],
                phone_number_sid=number_info["phone_number_sid"],
                subaccount_sid=subaccount_info["subaccount_sid"],
                webhook_urls=number_info["webhook_urls"],
                capabilities=number_info["capabilities"],
                area_code=area_code,
                country_code=country_code,
                created_at=datetime.now(),
                status="active"
            )

            # Step 4: Update hospital in database
            update_result = self.db.hospitals.update_one(
                {"id": hospital_id},
                {
                    "$set": {
                        "twilio_config": twilio_config_data.dict(),
                        "updated_at": datetime.now()
                    }
                }
            )

            if update_result.modified_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update hospital with Twilio configuration"
                )

            logger.info(f"✅ Complete setup finished for hospital {hospital_id}")

            return {
                "status": "success",
                "message": f"Phone number generated successfully for hospital {hospital_id}",
                "hospital_config": {
                    "hospital_id": hospital_id,
                    "hospital_name": hospital["hospital_name"],
                    "twilio_config": twilio_config_data.dict()
                },
                "phone_number": number_info["phone_number"],
                "webhook_url": number_info["webhook_urls"]["voice_webhook"]
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Setup failed for hospital {hospital_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Setup failed: {str(e)}"
            )

    async def get_hospital_twilio_config(self, hospital_id: str) -> Dict[str, Any]:
        """Get hospital's Twilio configuration"""
        try:
            hospital = self.db.hospitals.find_one({"id": hospital_id})

            if not hospital:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Hospital with ID {hospital_id} not found"
                )

            if not hospital.get("twilio_config"):
                # Return a successful response indicating no configuration instead of 404
                return {
                    "status": "not_found",
                    "hospital_id": hospital_id,
                    "hospital_name": hospital.get("hospital_name"),
                    "twilio_config": None
                }

            return {
                "status": "success",
                "hospital_id": hospital_id,
                "hospital_name": hospital["hospital_name"],
                "twilio_config": hospital["twilio_config"]
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error retrieving Twilio config for hospital {hospital_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving configuration: {str(e)}"
            )
