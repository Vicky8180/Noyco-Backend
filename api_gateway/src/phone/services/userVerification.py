# """
# User Verification Service for Phone Calls
# Handles verification of incoming calls against user_profile collection
# """

# import logging
# from typing import Optional, Dict, Any
# from api_gateway.database.db import get_database
# from pymongo import MongoClient

# logger = logging.getLogger(__name__)

# class UserVerificationService:
#     """Service to verify users for incoming phone calls"""
    
#     def __init__(self):
#         """Initialize database connection"""
#         self.db = get_database()
#         self.user_profiles = self.db.user_profiles
        
#     async def verify_user_by_phone(self, phone_number: str) -> Dict[str, Any]:
#         """
#         Verify if a user exists in user_profile collection by phone number
        
#         Args:
#             phone_number (str): The phone number to verify
            
#         Returns:
#             Dict containing verification result and user data if found
#         """
#         try:
#             # Clean the phone number (remove any formatting)
#             clean_phone = self._clean_phone_number(phone_number)
            
#             logger.info(f"Verifying user with phone number: {clean_phone}")
#             logger.info(f"Original phone number: {phone_number}")
            
#             # Search for user in user_profiles collection
#             user_profile = self.user_profiles.find_one({
#                 "phone": clean_phone
#             })
            
#             # Also try with original phone number in case it's stored with formatting
#             if not user_profile:
#                 user_profile = self.user_profiles.find_one({
#                     "phone": phone_number
#                 })
#                 logger.info(f"Tried original format: {phone_number}")
            
#             # Try with +91 prefix for Indian numbers
#             if not user_profile and clean_phone.startswith("82"):
#                 indian_format = "+91" + clean_phone
#                 user_profile = self.user_profiles.find_one({
#                     "phone": indian_format
#                 })
#                 logger.info(f"Tried Indian format: {indian_format}")
            
#             if user_profile:
#                 logger.info(f"User found for phone number {clean_phone}: {user_profile.get('id', 'unknown')}")
#                 return {
#                     "verified": True,
#                     "user_exists": True,
#                     "user_profile": user_profile,
#                     "message": "User verified successfully"
#                 }
#             else:
#                 logger.info(f"No user found for phone number: {clean_phone}")
#                 # Let's also log how many users are in the collection for debugging
#                 total_users = self.user_profiles.count_documents({})
#                 logger.info(f"Total users in user_profiles collection: {total_users}")
#                 return {
#                     "verified": False,
#                     "user_exists": False,
#                     "user_profile": None,
#                     "message": "User not found in system"
#                 }
                
#         except Exception as e:
#             logger.error(f"Error verifying user by phone {phone_number}: {str(e)}")
#             return {
#                 "verified": False,
#                 "user_exists": False,
#                 "user_profile": None,
#                 "message": f"Verification error: {str(e)}"
#             }
    
#     def _clean_phone_number(self, phone_number: str) -> str:
#         """
#         Clean phone number by removing formatting characters
        
#         Args:
#             phone_number (str): Raw phone number
            
#         Returns:
#             str: Cleaned phone number
#         """
#         if not phone_number:
#             return ""
            
#         # Remove common formatting characters
#         cleaned = phone_number.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        
#         # Handle Indian numbers specifically
#         if cleaned.startswith("91") and len(cleaned) == 12:
#             # Remove country code for Indian numbers (91xxxxxxxxxx -> xxxxxxxxxx)
#             cleaned = cleaned[2:]
#         elif cleaned.startswith("1") and len(cleaned) == 11:
#             # Remove country code for US numbers (1xxxxxxxxxx -> xxxxxxxxxx)
#             cleaned = cleaned[1:]
            
#         logger.info(f"Cleaned phone number: '{phone_number}' -> '{cleaned}'")
#         return cleaned
    
#     def get_premium_plan_message(self) -> str:
#         """
#         Get the message to play for users who don't have premium plan
        
#         Returns:
#             str: Message for non-premium users
#         """
#         return ("Thank you for calling. To access our AI assistant service, "
#                 "you need to purchase our premium plan. Please visit our website "
#                 "or contact our support team to upgrade your account. "
#                 "Thank you for your interest and have a great day!")
    
#     def get_user_not_found_message(self) -> str:
#         """
#         Get the message to play for users not found in system
        
#         Returns:
#             str: Message for unregistered users
#         """
#         return ("Thank you for calling. We couldn't find your phone number "
#                 "in our system. To access our AI assistant service, "
#                 "please register for our premium plan. Visit our website "
#                 "or contact our support team to get started. "
#                 "Thank you for your interest and have a great day!")
