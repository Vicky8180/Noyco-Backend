# api_gateway/src/billing/schema.py
from pydantic import BaseModel, validator
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

class PlanType(str, Enum):
    LITE = "lite"
    PRO = "pro"
    HOBBY = "hobby"
    BASIC = "basic"

class ServiceType(str, Enum):
    CHECKPOINT = "checkpoint"
    PRIMARY = "primary"
    CHECKLIST = "checklist"
    MEDICATION = "medication"
    NUTRITION = "nutrition"
    PRIVACY = "privacy"
    SUMMARY = "summary"
    HUMAN_ESCALATION = "human_escalation"

class PlanStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    
class ModelTier(str, Enum):
    GEMINI_1_5 = "gemini-1.5" 
    GPT_3_5 = "gpt-3.5"
    GPT_4 = "gpt-4"
    GPT_4O = "gpt-4o"
    
class UserRole(str, Enum):
    ADMIN = "admin"
    # HOSPITAL = "hospital"
    ASSISTANT = "assistant"
    INDIVIDUAL = "individual"

# Generic Plan Model
class Plan(BaseModel):
    id: str

    # Links plan to hospital/org/individual
    role_entity_id: str
    plan_type: PlanType
    status: PlanStatus = PlanStatus.ACTIVE

    # Payment reference
    payment_ref_id: Optional[str] = None

    # Core Limits
    max_agents: int
    rate_limit_per_minute: int
    max_context_length: int

    # Features
    selected_services: List[ServiceType] = []
    memory_stack: List[str] = []

    # AI Capabilities
    summarizer_available: bool = False
    human_escalation_available: bool = False
    model_tier: ModelTier

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        use_enum_values = True

# Request Models
class PlanSelectionRequest(BaseModel):
    plan_type: PlanType
    id: str
 
# class ServiceSelectionRequest(BaseModel):
#     hospital_id: str
#     services: List[str]

#     @validator('services')
#     def validate_services(cls, v):
#         if not v:
#             raise ValueError('At least one service must be selected')
#         return list(set(v))  # Remove duplicates

class IndividualPlanSelectionRequest(BaseModel):
    plan_type: PlanType
    individual_id: str

# Response Models
class PlanConfigResponse(BaseModel):
    plan_type: PlanType
    max_agents: int
    available_services: List[str]
    memory_stack: List[str]
    summarizer_available: bool
    human_escalation_available: bool
    model_tier: str
    max_context_length: int
    rate_limit_per_minute: int

class PlanDetailResponse(BaseModel):
    """Detailed plan information for display purposes"""
    plan_type: PlanType
    name: str
    description: str
    price_monthly: float
    price_yearly: float
    max_agents: int
    features: List[str]
    model_tier: str
    is_recommended: bool = False

class AvailablePlansResponse(BaseModel):
    """Response model for available plans based on user role"""
    plans: List[PlanDetailResponse]
    user_role: UserRole
    current_plan: Optional[PlanType] = None
    current_plan_details: Optional[PlanDetailResponse] = None

class AvailableServicesResponse(BaseModel):
    services: List[Dict[str, Any]]

# class HospitalPlanResponse(BaseModel):
#     id: str
#     hospital_id: str
#     plan_type: PlanType
#     status: PlanStatus
#     max_agents: int
#     available_services: List[str]
#     selected_services: List[str]
#     memory_stack: List[str]
#     summarizer_available: bool
#     human_escalation_available: bool
#     model_tier: str
#     max_context_length: int
#     rate_limit_per_minute: int
#     created_at: datetime
#     updated_at: datetime

class IndividualPlanResponse(BaseModel):
    """Response model for individual plan details"""
    id: str
    individual_id: str
    plan_type: PlanType
    status: PlanStatus
    max_agents: int
    available_services: List[str]
    selected_services: List[str]
    memory_stack: List[str]
    summarizer_available: bool
    human_escalation_available: bool
    model_tier: str
    max_context_length: int
    rate_limit_per_minute: int
    created_at: datetime
    updated_at: datetime
    plan_details: Optional[Dict[str, Any]] = None

# Database Models
# class HospitalPlan(BaseModel):
#     id: str
#     hospital_id: str
#     hospital_unique_identity: str
#     plan_type: PlanType
#     status: PlanStatus = PlanStatus.ACTIVE
#     max_agents: int
#     available_services: List[str]
#     selected_services: List[str] = []
#     memory_stack: List[str]
#     summarizer_available: bool
#     human_escalation_available: bool
#     model_tier: str
#     max_context_length: int
#     rate_limit_per_minute: int
#     created_at: datetime
#     updated_at: datetime

class PlanUpdateHistory(BaseModel):
    id: str
    hospital_id: str
    previous_plan: PlanType
    new_plan: PlanType
    changed_by: str
    reason: Optional[str] = None
    created_at: datetime

