# api_gateway/src/billing/main.py
"""
Billing Module for Healthcare Platform API Gateway

This module handles hospital plan management including:
- Plan type selection (LITE/PRO)
- Service selection and configuration
- Plan configuration management
- Billing-related operations

The module integrates with the authentication system and provides
role-based access control for plan management operations.
"""

from .routes import router
from .controller import BillingController
from .schema import (
    PlanType, ServiceType, PlanStatus, ModelTier,
    PlanSelectionRequest, ServiceSelectionRequest, IndividualPlanSelectionRequest,
    PlanConfigResponse, AvailableServicesResponse, HospitalPlanResponse,
    HospitalPlan, PlanUpdateHistory, Plan,
    PlanDetailResponse, AvailablePlansResponse, UserRole, IndividualPlanResponse
)

__all__ = [
    "router",
    "BillingController",
    "PlanType",
    "ServiceType",
    "PlanStatus",
    "ModelTier",
    "Plan",
    "PlanSelectionRequest",
    "ServiceSelectionRequest",
    "IndividualPlanSelectionRequest",
    "PlanConfigResponse",
    "AvailableServicesResponse",
    "HospitalPlanResponse",
    "HospitalPlan",
    "PlanUpdateHistory",
    "PlanDetailResponse",
    "AvailablePlansResponse",
    "UserRole",
    "IndividualPlanResponse"
]
