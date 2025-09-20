# api_gateway/src/billing/controller.py
from fastapi import HTTPException, status
from typing import List, Dict, Optional, Any, cast
from datetime import datetime
import uuid

from .schema import (
    PlanType, ServiceType, PlanStatus, UserRole, ModelTier,
    PlanSelectionRequest, 
    # ServiceSelectionRequest,
    PlanConfigResponse, AvailableServicesResponse, 
    # HospitalPlanResponse,
    PlanUpdateHistory, PlanDetailResponse, AvailablePlansResponse,
    IndividualPlanResponse
)
from ...database.db import get_database
from ...utils.helperFunctions import generate_unique_id

# REPLACE existing PLAN_CONFIGS and PLAN_DETAILS definitions with role-specific dictionaries to avoid key collisions and allow LITE/PRO for both roles
# Hospital-specific configurations
PLAN_CONFIGS_HOSPITAL = {
    PlanType.LITE: {
        "max_agents": 5,
        "available_services": [
            "privacy", 
            "human_escalation", 
            "checklist", 
            "medication", 
            "nutrition"
        ],
        "memory_stack": ["standard"],
        "summarizer_available": False,
        "human_escalation_available": False,
        "model_tier": "basic",
        "max_context_length": 2000,
        "rate_limit_per_minute": 60,
    },
    PlanType.PRO: {
        "max_agents": 50,
        "available_services": [
            "privacy", 
            "human_escalation", 
            "checklist", 
            "medication", 
            "nutrition"
        ],
        "memory_stack": ["premium"],
        "summarizer_available": True,
        "human_escalation_available": True,
        "model_tier": "premium",
        "max_context_length": 8000,
        "rate_limit_per_minute": 300,
    },
}

# Individual-specific configurations
PLAN_CONFIGS_INDIVIDUAL = {
    PlanType.LITE: {
        "max_agents": 1,
        "available_services": ["basic_service"],
        "memory_stack": ["standard"],
        "summarizer_available": False,
        "human_escalation_available": False,
        "model_tier": "basic",
        "max_context_length": 1000,
        "rate_limit_per_minute": 30,
    },
    PlanType.PRO: {
        "max_agents": 2,
        "available_services": ["basic_service"],
        "memory_stack": ["standard"],
        "summarizer_available": True,
        "human_escalation_available": False,
        "model_tier": "advanced",
        "max_context_length": 4000,
        "rate_limit_per_minute": 120,
    },
}

# Hospital-specific display details
PLAN_DETAILS_HOSPITAL = {
    PlanType.LITE: {
        "name": "Lite Plan (Hospital)",
        "description": "Essential features for small healthcare organizations",
        "price_monthly": 499.0,
        "price_yearly": 4790.40,
        "max_agents": 5,
        "features": [
            "Basic patient management",
            "Standard memory stack",
            "Limited API access",
            "Email support",
        ],
        "model_tier": ModelTier.GEMINI_1_5,
    },
    PlanType.PRO: {
        "name": "Pro Plan (Hospital)",
        "description": "Advanced features for growing healthcare organizations",
        "price_monthly": 999.0,
        "price_yearly": 9590.40,
        "max_agents": 50,
        "features": [
            "Advanced patient management",
            "Premium memory stack",
            "Unlimited API access",
            "Priority support",
            "Custom integrations",
        ],
        "model_tier": ModelTier.GEMINI_1_5,
        "is_recommended": True,
    },
}

# Individual-specific display details
PLAN_DETAILS_INDIVIDUAL = {
    PlanType.LITE: {
        "name": "Lite Plan (Individual)",
        "description": "Standard features for individual healthcare providers",
        "price_monthly": 49.0,
        "price_yearly": 470.40,
        "max_agents": 1,
        "features": [
            "Standard patient management",
            "Basic memory stack",
            "Standard API access",
            "Email support",
        ],
        "model_tier": ModelTier.GEMINI_1_5,
        "is_recommended": True,
    },
    PlanType.PRO: {
        "name": "Pro Plan (Individual)",
        "description": "Extra capacity for busy individual practitioners",
        "price_monthly": 99.0,
        "price_yearly": 950.40,
        "max_agents": 2,
        "features": [
            "Basic patient management",
            "Limited memory stack",
            "Restricted API access",
            "Community support",
        ],
        "model_tier": ModelTier.GEMINI_1_5,
    },
}

# Helper that returns correct config/detail dict based on user role
ROLE_CONFIG_MAP = {
    # UserRole.HOSPITAL: PLAN_CONFIGS_HOSPITAL,
    UserRole.ADMIN: PLAN_CONFIGS_HOSPITAL,  # admins manage hospitals too
    UserRole.INDIVIDUAL: PLAN_CONFIGS_INDIVIDUAL,
}

ROLE_DETAILS_MAP = {
    # UserRole.HOSPITAL: PLAN_DETAILS_HOSPITAL,
    UserRole.ADMIN: PLAN_DETAILS_HOSPITAL,
    UserRole.INDIVIDUAL: PLAN_DETAILS_INDIVIDUAL,
}

class BillingController:
    """Core billing controller for plan and service management"""

    def __init__(self):
        self.db = get_database()
        self._create_indexes()

    def _create_indexes(self):
        """Create database indexes for optimal performance"""
        try:
            self.db.plans.create_index("hospital_id")
            self.db.plans.create_index("plan_type")
            self.db.plans.create_index("status")
            self.db.plan_update_history.create_index("hospital_id")
            
            # Additional index for individual plans now stored in `plans` collection
            self.db.plans.create_index("individual_id", unique=True)
        except Exception:
            pass  # Indexes might already exist

    async def get_individual_plan(self, individual_id: str) -> Optional[IndividualPlanResponse]:
        """Get individual plan details by individual_id"""
        try:
            # Find individual plan by individual_id
            individual_plan = self.db.plans.find_one({
                "individual_id": individual_id
            })

            # Legacy auto-creation logic removed to prevent unintended plan resurrection.
            # If no plan document exists, simply return None so that the UI shows no active subscription.

            if not individual_plan:
                # Return None if no plan found
                return None

            # Get the plan details for display
            plan_type = individual_plan.get("plan_type")
            plan_details = None
            if plan_type and plan_type in PLAN_DETAILS_INDIVIDUAL:
                plan_details = PLAN_DETAILS_INDIVIDUAL[PlanType(plan_type)]

            # Return the response
            return IndividualPlanResponse(
                id=individual_plan["id"],
                individual_id=individual_plan["individual_id"],
                plan_type=individual_plan["plan_type"],
                status=individual_plan["status"],
                max_agents=individual_plan.get("max_agents", 1),
                available_services=individual_plan.get("available_services", []),
                selected_services=individual_plan.get("selected_services", []),
                memory_stack=individual_plan.get("memory_stack", []),
                summarizer_available=individual_plan.get("summarizer_available", False),
                human_escalation_available=individual_plan.get("human_escalation_available", False),
                model_tier=individual_plan.get("model_tier", "basic"),
                max_context_length=individual_plan.get("max_context_length", 1000),
                rate_limit_per_minute=individual_plan.get("rate_limit_per_minute", 30),
                created_at=individual_plan["created_at"],
                updated_at=individual_plan["updated_at"],
                plan_details=plan_details
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving individual plan: {str(e)}"
            )

    async def select_individual_plan(self, individual_id: str, plan_type: PlanType, user_id: str) -> IndividualPlanResponse:
        """Select and create a plan for an individual"""
        try:
            # Verify individual exists
            individual = self.db.individuals.find_one({
                "id": individual_id
            })

            if not individual:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Individual not found"
                )

            # Get plan configuration
            if plan_type not in PLAN_CONFIGS_INDIVIDUAL:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid plan type"
                )

            plan_config = PLAN_CONFIGS_INDIVIDUAL[plan_type]  # type: ignore

            # Check if plan already exists
            existing_plan = self.db.plans.find_one({
                "individual_id": individual_id
            })

            current_time = datetime.utcnow()
            plan_data = {
                "individual_id": individual_id,
                "plan_type": plan_type.value,
                "status": PlanStatus.ACTIVE.value,
                "selected_services": [],
                "created_at": current_time,
                "updated_at": current_time,
                **plan_config
            }

            if existing_plan:
                # Update existing plan
                old_plan_type = existing_plan.get("plan_type")

                # Update plan
                self.db.plans.update_one(
                    {"id": existing_plan["id"]},
                    {"$set": plan_data}
                )
                plan_data["id"] = existing_plan["id"]
            else:
                # Create new plan
                plan_data["id"] = generate_unique_id("plan")
                self.db.plans.insert_one(plan_data)

            # Update individual's plan reference
            self.db.individuals.update_one(
                {"id": individual_id},
                {"$set": {
                    "plan": plan_type.value,
                    "updated_at": current_time
                }}
            )

            # Get the plan details for display
            plan_details = None
            if plan_type in PLAN_DETAILS_INDIVIDUAL:
                plan_details = PLAN_DETAILS_INDIVIDUAL[plan_type]

            # Return the response
            return IndividualPlanResponse(
                id=plan_data["id"],
                individual_id=individual_id,
                plan_type=plan_data["plan_type"],
                status=plan_data["status"],
                max_agents=plan_data.get("max_agents", 1),
                available_services=plan_data.get("available_services", []),
                selected_services=plan_data.get("selected_services", []),
                memory_stack=plan_data.get("memory_stack", []),
                summarizer_available=plan_data.get("summarizer_available", False),
                human_escalation_available=plan_data.get("human_escalation_available", False),
                model_tier=plan_data.get("model_tier", "basic"),
                max_context_length=plan_data.get("max_context_length", 1000),
                rate_limit_per_minute=plan_data.get("rate_limit_per_minute", 30),
                created_at=plan_data["created_at"],
                updated_at=plan_data["updated_at"],
                plan_details=plan_details
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error selecting individual plan: {str(e)}"
            )

    async def get_available_plans(self, user_role: UserRole, role_entity_id: Optional[str] = None) -> AvailablePlansResponse:
        """
        Get available plans based on user role
        
        For hospitals: LITE and PRO plans
        For individuals: LITE and PRO plans
        """
        try:
            # Determine available plans and detail dictionary based on role
            if user_role == UserRole.ADMIN:
                available_plan_types = [PlanType.LITE, PlanType.PRO]
            elif user_role == UserRole.INDIVIDUAL:
                available_plan_types = [PlanType.LITE, PlanType.PRO]
            else:
                available_plan_types = []

            plan_detail_source = ROLE_DETAILS_MAP.get(user_role, {})

            # Get current plan if any
            current_plan = None
            if role_entity_id:
                if user_role == UserRole.INDIVIDUAL:
                    plan_record = self.db.plans.find_one({"individual_id": role_entity_id})
                    if plan_record and "plan_type" in plan_record:
                        current_plan = PlanType(plan_record["plan_type"])

            current_plan_details = None
            if current_plan and current_plan in plan_detail_source:
                pd = plan_detail_source[current_plan]
                current_plan_details = PlanDetailResponse(
                    plan_type=current_plan,
                    name=pd["name"],
                    description=pd["description"],
                    price_monthly=pd["price_monthly"],
                    price_yearly=pd["price_yearly"],
                    max_agents=pd["max_agents"],
                    features=pd["features"],
                    model_tier=pd["model_tier"],
                    is_recommended=pd.get("is_recommended", False),
                )

            # Build list response
            plans = []
            for plan_type in available_plan_types:
                if plan_type in plan_detail_source:
                    pd = plan_detail_source[plan_type]
                    plans.append(
                        PlanDetailResponse(
                            plan_type=plan_type,
                            name=pd["name"],
                            description=pd["description"],
                            price_monthly=pd["price_monthly"],
                            price_yearly=pd["price_yearly"],
                            max_agents=pd["max_agents"],
                            features=pd["features"],
                            model_tier=pd["model_tier"],
                            is_recommended=pd.get("is_recommended", False),
                        )
                    )

            return AvailablePlansResponse(
                plans=plans,
                user_role=user_role,
                current_plan=current_plan,
                current_plan_details=current_plan_details,
            )
        
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving available plans: {str(e)}"
            )

    async def get_plan_types(self) -> Dict[str, PlanConfigResponse]:
        """Get all available plan types with their configurations"""
        try:
            plan_configs = {}
            for plan_type, config in PLAN_CONFIGS_HOSPITAL.items():
                plan_configs[plan_type.value] = PlanConfigResponse(
                    plan_type=plan_type,
                    **config
                )
            return plan_configs
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving plan configurations: {str(e)}"
            )

    # async def get_available_services(self, user_id: str = None, role_entity_id: str = None) -> AvailableServicesResponse:
    #     """Get available services based on plan type"""
    #     try:
    #         # Get services from hospital or individual plan
    #         services = [
    #             {
    #                 "id": "privacy", 
    #                 "name": "Privacy Protection", 
    #                 "description": "Ensures sensitive patient data is properly anonymized and protected",
    #                 "is_default": True
    #             },
    #             {
    #                 "id": "human_escalation", 
    #                 "name": "Human Escalation", 
    #                 "description": "Automatically escalates complex cases to human specialists when needed",
    #                 "is_default": True
    #             },
    #             {
    #                 "id": "checklist", 
    #                 "name": "Clinical Checklists", 
    #                 "description": "Generates dynamic checklists based on clinical guidelines",
    #                 "is_default": True
    #             },
    #             {
    #                 "id": "medication", 
    #                 "name": "Medication Management", 
    #                 "description": "Provides advanced medication recommendations and checks for contraindications"
    #             },
    #             {
    #                 "id": "nutrition", 
    #                 "name": "Nutrition Analysis", 
    #                 "description": "Offers detailed nutrition guidance and dietary recommendations"
    #             }
    #         ]

    #         # If hospital or individual plan exists, check which services are available
    #         if role_entity_id:
    #             hospital_plan = self.db.plans.find_one({"hospital_id": role_entity_id})
    #             if hospital_plan:
    #                 plan_type = hospital_plan.get("plan_type")
    #                 selected_services = hospital_plan.get("selected_services", [])
                    
    #                 # Mark services with appropriate flags
    #                 for service in services:
    #                     # Mark if service is selected
    #                     service["is_selected"] = service["id"] in selected_services
                        
    #                     # Default services are always selected and available
    #                     if service.get("is_default", False):
    #                         service["is_available"] = True
    #                     # For lite plan, handle optional services
    #                     elif plan_type == PlanType.LITE.value:
    #                         # Optional services in lite plan
    #                         if service["id"] in ["medication", "nutrition"]:
    #                             # If this one is selected, it's available
    #                             if service["id"] in selected_services:
    #                                 service["is_available"] = True
    #                             # If another optional is selected, this one is not available
    #                             elif any(s in selected_services for s in ["medication", "nutrition"] if s != service["id"]):
    #                                 service["is_available"] = False
    #                             # If no optional is selected yet, it's available
    #                             else:
    #                                 service["is_available"] = True
    #                     # For pro plan or other types, all services are available
    #                     else:
    #                         service["is_available"] = True
    #             else:
    #                 # No plan found, mark defaults as selected and all as available
    #                 for service in services:
    #                     service["is_selected"] = service.get("is_default", False)
    #                     service["is_available"] = True
    #         else:
    #             # No hospital/user ID provided, mark defaults as selected and all as available
    #             for service in services:
    #                 service["is_selected"] = service.get("is_default", False)
    #                 service["is_available"] = True

    #         return AvailableServicesResponse(services=services)

    #     except Exception as e:
    #         raise HTTPException(
    #             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #             detail=f"Error retrieving available services: {str(e)}"
    #         )

    # async def select_plan(self, request: PlanSelectionRequest, user_id: str) -> HospitalPlanResponse:
    #     """Select and create a plan for a hospital"""
    #     try:
    #         # Verify hospital exists
    #         hospital = self.db.hospitals.find_one({
    #             "id": request.id
    #         })

    #         if not hospital:
    #             raise HTTPException(
    #                 status_code=status.HTTP_404_NOT_FOUND,
    #                 detail="Hospital with provided unique identity not found"
    #             )

    #         # Get plan configuration
    #         if request.plan_type not in PLAN_CONFIGS_HOSPITAL:
    #             raise HTTPException(
    #                 status_code=status.HTTP_400_BAD_REQUEST,
    #                 detail="Invalid plan type"
    #             )

    #         plan_config = PLAN_CONFIGS_HOSPITAL[request.plan_type]  # type: ignore

    #         # Check if plan already exists
    #         existing_plan = self.db.plans.find_one({
    #             "hospital_id": hospital["id"]
    #         })

    #         current_time = datetime.utcnow()
            
    #         # Set default selected services
    #         default_services = ["privacy", "human_escalation", "checklist"]
            
    #         plan_data = {
    #             "hospital_id": hospital["id"],
    #             "plan_type": request.plan_type.value,
    #             "status": PlanStatus.ACTIVE.value,
    #             "selected_services": default_services,
    #             "created_at": current_time,
    #             "updated_at": current_time,
    #             **plan_config
    #         }

    #         if existing_plan:
    #             # Update existing plan
    #             old_plan_type = existing_plan.get("plan_type")

    #             # Create history record if plan type changed
    #             if old_plan_type != request.plan_type.value:
    #                 await self._create_plan_history(
    #                     hospital_id=hospital["id"],
    #                     previous_plan=old_plan_type,
    #                     new_plan=request.plan_type.value,
    #                     changed_by=user_id,
    #                     reason="Plan type change"
    #                 )

    #             # If there were previously selected optional services, carry them forward if possible
    #             if "selected_services" in existing_plan:
    #                 current_selected = existing_plan["selected_services"]
                    
    #                 # Keep optional services if compatible with new plan
    #                 optional_services = [s for s in current_selected if s in ["medication", "nutrition"]]
                    
    #                 # For lite plan, only keep one optional service
    #                 if request.plan_type == PlanType.LITE and len(optional_services) > 1:
    #                     optional_services = optional_services[:1]  # Keep only the first one
                    
    #                 # Combine default services with compatible optional services
    #                 plan_data["selected_services"] = list(set(default_services + optional_services))

    #             # Update plan
    #             self.db.plans.update_one(
    #                 {"id": existing_plan["id"]},
    #                 {"$set": plan_data}
    #             )
    #             plan_data["id"] = existing_plan["id"]
    #         else:
    #             # Create new plan
    #             plan_data["id"] = generate_unique_id("plan")
    #             self.db.plans.insert_one(plan_data)

    #         # Update hospital's plan reference
    #         self.db.hospitals.update_one(
    #             {"id": hospital["id"]},
    #             {"$set": {
    #                 "plan": request.plan_type.value,
    #                 "updated_at": current_time
    #             }}
    #         )

    #         return HospitalPlanResponse(**plan_data)

    #     except HTTPException:
    #         raise
    #     except Exception as e:
    #         raise HTTPException(
    #             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #             detail=f"Error selecting plan: {str(e)}"
    #         )

    # async def select_services(self, request: ServiceSelectionRequest, user_id: str) -> HospitalPlanResponse:
    #     """Select services for a hospital's plan"""
    #     try:
    #         # Get hospital plan
    #         # First try to locate by unique identity
    #         hospital_plan = self.db.plans.find_one({
    #             "hospital_id": request.hospital_id
    #         })

    #         # No plan found by hospital_id
    #         # (legacy hospital_unique_identity support removed)

    #         if not hospital_plan:
    #             raise HTTPException(
    #                 status_code=status.HTTP_404_NOT_FOUND,
    #                 detail="Hospital plan not found. Please select a plan first."
    #             )

    #         plan_type = hospital_plan.get("plan_type")
            
    #         # Make sure default services are always included
    #         default_services = ["privacy", "human_escalation", "checklist"]
    #         requested_services = list(set(request.services + default_services))
            
    #         # Apply plan-specific restrictions
    #         if plan_type == PlanType.LITE.value:
    #             # For Lite plan, only allow one optional service
    #             optional_services = [s for s in requested_services if s in ["medication", "nutrition"]]
    #             if len(optional_services) > 1:
    #                 raise HTTPException(
    #                     status_code=status.HTTP_400_BAD_REQUEST,
    #                     detail="Lite plan can only select one optional service (medication or nutrition)"
    #                 )
                    
    #         # Update selected services
    #         current_time = datetime.utcnow()
    #         self.db.plans.update_one(
    #             {"id": hospital_plan["id"]},
    #             {"$set": {
    #                 "selected_services": requested_services,
    #                 "updated_at": current_time
    #             }}
    #         )

    #         # Get updated plan
    #         updated_plan = self.db.plans.find_one({
    #             "id": hospital_plan["id"]
    #         })

    #         return HospitalPlanResponse(**updated_plan)

    #     except HTTPException:
    #         raise
    #     except Exception as e:
    #         raise HTTPException(
    #             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #             detail=f"Error selecting services: {str(e)}"
    #         )

    # async def get_hospital_plan(self, hospital_id: str) -> HospitalPlanResponse:
    #     """Get hospital plan details by hospital_id"""
    #     try:
    #         # Find hospital plan by hospital_id
    #         hospital_plan = self.db.plans.find_one({
    #             "hospital_id": hospital_id
    #         })

    #         # No legacy hospital_unique_identity fallback

    #         if not hospital_plan:
    #             raise HTTPException(
    #                 status_code=status.HTTP_404_NOT_FOUND,
    #                 detail="Hospital plan not found"
    #             )

    #         return HospitalPlanResponse(**hospital_plan)

    #     except HTTPException:
    #         raise
    #     except Exception as e:
    #         raise HTTPException(
    #             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #             detail=f"Error retrieving hospital plan: {str(e)}"
    #         )

    # async def get_hospital_by_id(self, hospital_id: str) -> Optional[Dict[str, Any]]:
    #     """Get hospital information by ID"""
    #     try:
    #         hospital = self.db.hospitals.find_one({"id": hospital_id})
    #         return hospital
    #     except Exception as e:
    #         raise HTTPException(
    #             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #             detail=f"Error retrieving hospital information: {str(e)}"
    #         )

    async def get_assistant_by_id(self, assistant_id: str) -> Optional[Dict[str, Any]]:
        """Get assistant information by ID"""
        try:
            assistant = self.db.assistants.find_one({"id": assistant_id})
            return assistant
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving assistant information: {str(e)}"
            )

    # async def _create_plan_history(self, hospital_id: str, previous_plan: str, new_plan: str, changed_by: str, reason: str = None):
    #     """Create plan update history record"""
    #     try:
    #         history_data = {
    #             "id": generate_unique_id("history"),
    #             "hospital_id": hospital_id,
    #             "previous_plan": previous_plan,
    #             "new_plan": new_plan,
    #             "changed_by": changed_by,
    #             "reason": reason,
    #             "created_at": datetime.utcnow()
    #         }
    #         self.db.plan_update_history.insert_one(history_data)
    #     except Exception:
    #         # Don't fail the main operation if history logging fails
    #         pass
