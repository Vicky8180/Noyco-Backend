from fastapi import HTTPException, status
from passlib.context import CryptContext
from datetime import datetime
from typing import Dict, Any, List, Optional
import uuid
from .schema import *
from fastapi.encoders import jsonable_encoder
from .schema import (RegistrationType, PlanType, UserRole)
from ...database.db import get_database
from ...utils.helperFunctions import generate_unique_id
from pymongo.errors import DuplicateKeyError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthController:
    """Core authentication controller for user management"""

    def __init__(self):
        self.db = get_database()

    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        return pwd_context.verify(plain_password, hashed_password)

    # async def register_hospital(self, request: RegistrationRequest) -> Dict[str, Any]:
    #     """Register a new hospital and create admin user"""
    #     # Check if hospital already exists
    #     existing_hospital = self.db.hospitals.find_one({
    #         "$or": [
    #             {"email": request.email},
    #             {"name": request.name}
    #         ]
    #     })

    #     if existing_hospital:
    #         raise HTTPException(
    #             status_code=status.HTTP_400_BAD_REQUEST,
    #             detail="Hospital with this email or identity already exists"
    #         )

    #     # Create hospital
    #     hospital_id = generate_unique_id("hospital")

    #     # Use hospital_name as admin_name if not provided
    #     admin_name = request.admin_name if hasattr(request, 'admin_name') and request.admin_name else request.hospital_name

    #     # Set default values for optional fields
    #     phone = request.phone if hasattr(request, 'phone') and request.phone else "Not provided"
    #     website_link = request.website_link if hasattr(request, 'website_link') and request.website_link else ""

    #     # Always set hospital status to ACTIVE regardless of plan
    #     hospital_status = HospitalStatus.ACTIVE

    #     # Generate unique hospital identity
    #     hospital_unique_identity = generate_unique_id("hosp")

    #     hospital = Hospital(
    #         id=hospital_id,
    #         name=request.hospital_name,
    #         email=request.email,
    #         password_hash=self.hash_password(request.password),
    #         phone=phone,
    #         website_link=website_link,
    #         plan=request.plan,
    #         status=hospital_status,
    #         created_at=datetime.utcnow(),
    #         updated_at=datetime.utcnow()
    #     )

    #     self.db.hospitals.insert_one(hospital.dict())

    #     # Create admin user
    #     admin_user_id = generate_unique_id("user")
    #     admin_user = User(
    #         id=admin_user_id,
    #         email=request.email,
    #         password_hash=hospital.password_hash,
    #         name=admin_name,
    #         role=UserRole.HOSPITAL,
    #         role_entity_id=hospital_id,
    #         department="Administration",
    #         created_at=datetime.utcnow(),
    #         updated_at=datetime.utcnow()
    #     )

    #     self.db.users.insert_one(admin_user.dict())

    #     return {
    #         "user_id": admin_user_id,
    #         "id": hospital_id,
    #         "email": request.email,
    #         "plan": request.plan
    #     }



    # async def register(self, request: RegistrationRequest) -> Dict[str, Any]:
    #     """Register a new hospital or individual with an admin user"""

    # # Check for duplicate email in users
    #     if self.db.users.find_one({"email": request.email}):
    #         raise HTTPException(
    #             status_code=status.HTTP_400_BAD_REQUEST,
    #             detail="User with this email already exists"
    #         )

    # # Common fields
    #     password_hash = self.hash_password(request.password)
    #     created_at = updated_at = datetime.utcnow()

    #     # If organisation, register in hospitals
    #     if request.type == RegistrationType.ORGANIZATION:
    #         existing = self.db.hospitals.find_one({
    #         "$or": [{"email": request.email}, {"name": request.name}]
    #         })
    #         if existing:
    #             raise HTTPException(
    #             status_code=status.HTTP_400_BAD_REQUEST,
    #             detail="Hospital with this email or name already exists"
    #         )

    #         hospital_id = generate_unique_id("hospital")
    #         hospital_identity = generate_unique_id("hosp")
    #         hospital = Hospital(
    #         id=hospital_id,
    #         name=request.name,
    #         email=request.email,
    #         password_hash=password_hash,
    #         phone=request.phone or "Not provided",
    #         website_link=request.website_link or "https://example.com",
    #         plan=request.plan,
    #         status=HospitalStatus.ACTIVE,
    #         created_at=created_at,
    #         updated_at=updated_at
    #     )
    #         self.db.hospitals.insert_one(hospital.dict())

    #     # Create hospital admin user
    #         admin_user_id = generate_unique_id("user")
    #         admin_user = User(
    #         id=admin_user_id,
    #         email=request.email,
    #         password_hash=password_hash,
    #         name=request.admin_name or request.name,
    #         role=UserRole.HOSPITAL,
    #         role_entity_id=hospital_id,
    #         department="Administration",
    #         created_at=created_at,
    #         updated_at=updated_at
    #     )
    #         self.db.users.insert_one(admin_user.dict())

    #         return {
    #         "user_id": admin_user_id,
    #         "id": hospital_id,
    #         "type": "organisation",
    #         "email": request.email,
    #         "plan": request.plan
    #     }

    # # If individual, register in individuals
    #     elif request.type == RegistrationType.INDIVIDUAL:
    #         individual_id = generate_unique_id("individual")
    #         individual = {
    #         "id": individual_id,
    #         "name": request.name,
    #         "email": request.email,
    #         "password_hash": password_hash,
    #         "phone": request.phone or "Not provided",
    #         "created_at": created_at,
    #         "updated_at": updated_at
    #     }
    #         self.db.individuals.insert_one(individual)

    #         user_id = generate_unique_id("user")
    #         user = User(
    #         id=user_id,
    #         email=request.email,
    #         password_hash=password_hash,
    #         name=request.name,
    #         role=UserRole.INDIVIDUAL,
    #         role_entity_id=individual_id,
    #         department=None,
    #         created_at=created_at,
    #         updated_at=updated_at
    #     )
    #         self.db.users.insert_one(user.dict())

    #         return {
    #         "user_id": user_id,
    #         "id": individual_id,
    #         "type": "individual",
    #         "email": request.email,
    #         "plan": request.plan
    #     }

    #     else:
    #         raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST,
    #         detail="Invalid registration type"
    #     )




    async def register(self, request: RegistrationRequest) -> Dict[str, Any]:
        """Register a new hospital or individual with an admin user"""

    # Check for duplicate email in users
        if self.db.users.find_one({"email": request.email}):
            raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )

    # Common fields
        password_hash = self.hash_password(request.password)
        created_at = updated_at = datetime.utcnow()

    # Only individual registration is supported now
        if request.type == RegistrationType.INDIVIDUAL:
            individual_id = generate_unique_id("individual")
            individual = {
            "id": individual_id,
            "name": request.name,
            "email": request.email,
            "password_hash": password_hash,
            "phone": request.phone or "Not provided",
            "created_at": created_at,
            "updated_at": updated_at
        }

            try:
                self.db.individuals.insert_one(jsonable_encoder(individual))
            except DuplicateKeyError:
                raise HTTPException(status_code=400, detail="Email already registered")

            user_id = generate_unique_id("user")
            user = User(
            id=user_id,
            email=request.email,
            password_hash=password_hash,
            name=request.name,
            role=UserRole.INDIVIDUAL,
            role_entity_id=individual_id,
            department=None,
            created_at=created_at,
            updated_at=updated_at
        )

            self.db.users.insert_one(jsonable_encoder(user))

            return {
            "user_id": user_id,
            "id": individual_id,
            "type": "individual",
            "email": request.email,
            "plan": request.plan
        }

        else:
            raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid registration type"
        )





    async def login(self, request: LoginRequest) -> Dict[str, Any]:
        """Authenticate user and return user data"""
        # Find user
        user = self.db.users.find_one({"email": request.email})
        if not user or not self.verify_password(request.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )

        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated"
            )

        # Require e-mail verification
        if not user.get("email_verified", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email not verified"
            )


        plan_type: Optional[PlanType] = None

        # Check user role to determine where to get plan information
        if user["role"] == UserRole.ADMIN.value:
            # Admin users don't have plan restrictions
            plan_type = None
        # elif user["role"] == UserRole.HOSPITAL.value:
        #     # Get hospital info
        #     hospital = self.db.hospitals.find_one({"id": user["role_entity_id"]})
        #     if not hospital:
        #         raise HTTPException(
        #             status_code=status.HTTP_404_NOT_FOUND,
        #             detail="Hospital not found"
        #         )

        #     # Get plan from hospital
        #     plan = hospital.get("plan")
        #     plan_type = PlanType(plan) if plan else None
        elif user["role"] == UserRole.INDIVIDUAL.value:
            # Get individual user info
            individual = self.db.individuals.find_one({"id": user["role_entity_id"]})
            if not individual:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Individual account not found"
                )

            # Get plan from individual
            plan = individual.get("plan")
            plan_type = PlanType(plan) if plan else None
        else:
            # Assistant users inherit plan from their individual owner
            assistant = self.db.assistants.find_one({"id": user["role_entity_id"]})
            if not assistant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Assistant not found"
                )

            individual = self.db.individuals.find_one({"id": assistant["individual_id"]})
            if not individual:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Individual not found"
                )

            # Get plan from individual
            plan = individual.get("plan")
            plan_type = PlanType(plan) if plan else None

        # Update last login timestamp
        self.db.users.update_one(
            {"id": user["id"]},
            {"$set": {"last_login": datetime.utcnow()}}
        )

        return {
            "user_id": user["id"],
            "role_entity_id": user["role_entity_id"],
            "email": user["email"],
            "role": UserRole(user["role"]),
            "plan": plan_type
        }

    async def get_user_data_for_token(self, user_id: str, role_entity_id: str) -> Dict[str, Any]:
        """Get user data needed for token generation"""
        user = self.db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Get role
        role = UserRole(user["role"])
        plan_type = None

        # Check user role to determine where to get plan information
        if role == UserRole.ADMIN:
            # Admin users don't have plan restrictions
            pass
        # elif role == UserRole.HOSPITAL:
        #     # Get hospital info
        #     hospital = self.db.hospitals.find_one({"id": role_entity_id})
        #     if not hospital:
        #         raise HTTPException(
        #             status_code=status.HTTP_404_NOT_FOUND,
        #             detail="Hospital not found"
        #         )

        #     # Get plan from hospital
        #     plan = hospital.get("plan")
        #     plan_type = PlanType(plan) if plan else None
        elif role == UserRole.INDIVIDUAL:
            # Get individual user info
            individual = self.db.individuals.find_one({"id": role_entity_id})
            if not individual:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Individual account not found"
                )

            # Get plan from individual
            plan = individual.get("plan")
            plan_type = PlanType(plan) if plan else None
        elif role == UserRole.ASSISTANT:
            # Assistant users inherit plan from their individual owner
            assistant = self.db.assistants.find_one({"id": role_entity_id})
            if not assistant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Assistant not found"
                )

            individual = self.db.individuals.find_one({"id": assistant["individual_id"]})
            if not individual:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Individual not found"
                )

            # Get plan from individual
            plan = individual.get("plan")
            plan_type = PlanType(plan) if plan else None

        return {
            "role": role,
            "email": user["email"],
            "plan": plan_type
        }

    async def update_password(self, user_id: str, request: PasswordUpdateRequest) -> Dict[str, str]:
        """Update user password"""
        user = self.db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Check if user is an OAuth user (no password)
        if not user.get("password_hash", "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot update password for OAuth accounts. Password changes are not supported for accounts that logged in via Google or other social providers."
            )

        if not self.verify_password(request.current_password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )

        new_password_hash = self.hash_password(request.new_password)
        self.db.users.update_one(
            {"id": user_id},
            {"$set": {"password_hash": new_password_hash, "updated_at": datetime.utcnow()}}
        )

        # If this is a hospital admin, also update hospital password
        # if user["role"] == UserRole.HOSPITAL.value:
        #     self.db.hospitals.update_one(
        #         {"id": user["hospital_id"]},
        #         {"$set": {"password_hash": new_password_hash, "updated_at": datetime.utcnow()}}
        #     )

        return {"message": "Password updated successfully"}

    async def create_assistant(self, role_entity_id: str, request: AssistantCreationRequest) -> UserResponse:
        """Create assistant user"""
        # Check if assistant already exists
        print(1)
        existing_user = self.db.users.find_one({"email": request.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )

        # Verify individual exists and is active
        print(2)
        individual = self.db.individuals.find_one({"id": role_entity_id})
        print(3)
        if not individual:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid individual"
            )

        # Generate unique IDs
        print(4)
        user_id = generate_unique_id("user")
        assistant_id = generate_unique_id("assistant")

        # Create assistant user in users collection
        user = User(
            id=user_id,
            email=request.email,
            password_hash=self.hash_password(request.password),
            name=request.name,
            role=UserRole.ASSISTANT,  # Always ASSISTANT
            role_entity_id=assistant_id,
            department=request.department,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        print(5)

        self.db.users.insert_one(user.dict())
        print(6)

        # Create assistant record in assistants collection
        assistant = Assistant(
            id=assistant_id,
            name=request.name,
            email=request.email,
            phone=request.phone,
            department=request.department,
            individual_id=role_entity_id,  # Changed from hospital_id
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        print(7)

        self.db.assistants.insert_one(assistant.dict())
        print(8)

        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            role_entity_id=user.role_entity_id,
            department=user.department,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=datetime.utcnow()
        )

    async def get_assistants(self, role_entity_id: str) -> List[AssistantResponse]:
        """Get all assistants for an individual"""
        assistants = []
        cursor = self.db.assistants.find({"individual_id": role_entity_id, "is_active": True})

        for assistant_doc in cursor:
            # Convert MongoDB _id to string
            # if "_id" in assistant_doc:
            #     assistant_doc["id"] = str(assistant_doc["_id"])

            assistants.append(AssistantResponse(
                id=assistant_doc["id"],
                email=assistant_doc["email"],
                name=assistant_doc["name"],
                phone=assistant_doc.get("phone"),
                department=assistant_doc.get("department"),
                individual_id=assistant_doc["individual_id"],  # Changed from hospital_id
                is_active=assistant_doc.get("is_active", True),
                created_at=assistant_doc["created_at"],
                updated_at=assistant_doc["updated_at"]
            ))

        return assistants

    async def get_assistant(self, assistant_id: str, individual_id: str) -> AssistantResponse:
        """Get a specific assistant by ID"""
        # Assistants are stored with their unique identifier under the "id" field.
        # Earlier code erroneously queried the non-existent "assistant_id" field.
        assistant_doc = self.db.assistants.find_one({
            "id": assistant_id,
            "individual_id": individual_id  # Changed from hospital_id
        })

        if not assistant_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assistant not found"
            )

        # Convert MongoDB _id to string
        if "_id" in assistant_doc:
            assistant_doc["id"] = str(assistant_doc["_id"])

        return AssistantResponse(
            id=assistant_doc["id"],
            email=assistant_doc["email"],
            name=assistant_doc["name"],
            phone=assistant_doc.get("phone"),
            department=assistant_doc.get("department"),
            individual_id=assistant_doc["individual_id"],  # Changed from hospital_id
            is_active=assistant_doc.get("is_active", True),
            created_at=assistant_doc["created_at"],
            updated_at=assistant_doc["updated_at"]
        )

    async def update_assistant(self, assistant_id: str, role_entity_id: str,
                              request: AssistantUpdateRequest) -> AssistantResponse:
        """Update assistant details"""
        # Find the assistant
        print(assistant_id, role_entity_id)
        assistant_doc = self.db.assistants.find_one({
            "id": assistant_id,
            "individual_id": role_entity_id  # Changed from hospital_id
        })

        if not assistant_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assistant not found"
            )

        # Find the user associated with this assistant.
        # Older assistant records may lack the "user_id" field, so fall back to
        # locating the user by role_entity_id.
        user_id = assistant_doc.get("user_id")

        if user_id:
            user = self.db.users.find_one({"id": user_id})
        else:
            # Legacy data fallback: try to locate user by role_entity_id (assistant id)
            user = self.db.users.find_one({"role_entity_id": assistant_id})
            if user:
                user_id = user["id"]
                # Patch the assistant document so this lookup is fast next time
                self.db.assistants.update_one(
                    {"id": assistant_id, "individual_id": role_entity_id},  # Changed from hospital_id
                    {"$set": {"user_id": user_id}}
                )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User record for assistant not found"
            )

        # Check if email is being changed and if it's already in use
        if request.email != assistant_doc["email"]:
            existing_user = self.db.users.find_one({
                "email": request.email,
                "id": {"$ne": user["id"]}  # Not the current user
            })
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email is already in use by another user"
                )

        # Update the assistant in assistants collection
        update_data = {
            "name": request.name,
            "email": request.email,
            "phone": request.phone,
            "department": request.department,
            "updated_at": datetime.utcnow()
        }

        # Use the "assistant_id" field (not MongoDB _id) to locate the document
        # because assistants are stored with a custom primary key generated by
        # generate_unique_id when they are created. Using _id here would never
        # match and the update would silently fail.
        self.db.assistants.update_one(
            {"id": assistant_id, "individual_id": role_entity_id},  # Changed from hospital_id
            {"$set": update_data}
        )

        # Update the user record
        user_update = {
            "name": request.name,
            "email": request.email,
            "department": request.department,
            "updated_at": datetime.utcnow()
        }

        # Update password if provided
        if request.password:
            user_update["password_hash"] = self.hash_password(request.password)

        self.db.users.update_one(
            {"id": user_id},
            {"$set": user_update}
        )

        # Get updated assistant
        updated_assistant = self.db.assistants.find_one({
            "id": assistant_id,
            "individual_id": role_entity_id  # Changed from hospital_id
        })

        if "_id" in updated_assistant:
            updated_assistant["id"] = str(updated_assistant["_id"])

        return AssistantResponse(
            id=updated_assistant["id"],
            email=updated_assistant["email"],
            name=updated_assistant["name"],
            phone=updated_assistant.get("phone"),
            department=updated_assistant.get("department"),
            individual_id=updated_assistant["individual_id"],  # Changed from hospital_id
            is_active=updated_assistant.get("is_active", True),
            created_at=updated_assistant["created_at"],
            updated_at=updated_assistant["updated_at"]
        )

    async def delete_assistant(self, assistant_id: str, role_entity_id: str) -> Dict[str, str]:
        """Delete an assistant"""
        # Find the assistant
        assistant_doc = self.db.assistants.find_one({
            "id": assistant_id,
            "individual_id": role_entity_id  # Changed from hospital_id
        })

        if not assistant_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assistant not found"
            )

        # Get the user ID associated with this assistant
        assistant_id = assistant_doc["id"]

        # Hard-delete assistant document
        self.db.assistants.delete_one({"id": assistant_id, "individual_id": role_entity_id})  # Changed from hospital_id

        # Remove the corresponding user account as well
        self.db.users.delete_one({"role_entity_id": assistant_id})

        return {"message": "Assistant successfully deleted", "assistant_id": assistant_id}

    # ---------------------------------------------------------------------
    # OTP / Email verification helpers
    # ---------------------------------------------------------------------
    def find_user_by_email(self, email: str):
        """Return raw user doc (sync)"""
        return self.db.users.find_one({"email": email})

    async def mark_email_verified(self, email: str):
        """Set email_verified True"""
        self.db.users.update_one({"email": email}, {"$set": {"email_verified": True}})
