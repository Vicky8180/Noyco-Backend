# api_gateway/src/billing/routes.py
from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from typing import Dict, List, Union
from .controller import BillingController
from ...middlewares.jwt_auth import JWTAuthController
from .schema import (
    PlanSelectionRequest, 
    # ServiceSelectionRequest, I
    IndividualPlanSelectionRequest,
    PlanConfigResponse, AvailableServicesResponse, 
    # HospitalPlanResponse,
    UserRole, AvailablePlansResponse, IndividualPlanResponse, PlanType, PlanStatus
)

router = APIRouter(prefix="/billing", tags=["Billing"])
billing_controller = BillingController()
jwt_auth = JWTAuthController()
@router.get("/plan/current", response_model=IndividualPlanResponse)
async def get_current_individual_plan(
    current_user = Depends(jwt_auth.get_current_user)
):
    """Return the caller's current individual subscription details.

    Behaviour (current release):
    - Individuals: returns their plan document from DB
    - Other roles: 403 (hospital billing is disabled)
    """

    # Restrict to individual users in this release
    if current_user.role != UserRole.INDIVIDUAL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only individual accounts can view current subscription in this release")

    plan = await billing_controller.get_individual_plan(current_user.role_entity_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan



@router.get("/plan", response_model=AvailablePlansResponse)
async def get_available_plans(
    current_user = Depends(jwt_auth.get_current_user)
):
    """
    Get available plans based on user role.

    Returns different plan options based on the user's role:
    - For individuals: new Leapply plans (1m, 3m, 6m)
    - For admins: same individual catalog (hospital billing disabled this release)
    
    Also includes the user's current plan if they have one.
    """
    # Normalize role which may come as Enum or string
    role_str = str(current_user.role)
    if "." in role_str:
        role_str = role_str.split(".")[-1]
    role_str = role_str.lower()

    # Guard: hospital billing disabled for this release
    if role_str == "hospital":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hospital billing is disabled for this release")

    # Only individual and admin are supported here; assistants denied
    if role_str not in ("individual", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions to view plans")

    user_role_enum = UserRole.INDIVIDUAL if role_str == "individual" else UserRole.ADMIN

    return await billing_controller.get_available_plans(
        user_role=user_role_enum,
        role_entity_id=current_user.role_entity_id
    )



@router.get("/services", response_model=AvailableServicesResponse)
async def get_available_services(
    current_user = Depends(jwt_auth.get_current_user)
):
    """Get available services based on the user's current plan"""
    # Guard: hospital service selection disabled for this release
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Service catalog is not available in this release")

# @router.post("/services/select", response_model=HospitalPlanResponse)
# async def select_services(
#     request: ServiceSelectionRequest,
#     current_user = Depends(jwt_auth.get_current_user),
#     csrf_token: str = Header(..., alias="X-CSRF-Token")
# ):
#     """Select services for a hospital's plan"""
#     # Only hospital admins can select services
#     if current_user.role not in [UserRole.HOSPITAL, UserRole.ADMIN]:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN, 
#             detail="Only hospital administrators can select services"
#         )
    
#     try:
#         # For hospital users, make sure they only update their own hospital
#         if current_user.role == UserRole.HOSPITAL:
#             if current_user.role_entity_id != request.hospital_id:
#                 raise HTTPException(
#                     status_code=status.HTTP_403_FORBIDDEN,
#                     detail="Cannot modify services for other hospitals"
#                 )
        
#         # Check if plan exists and is active
#         hospital_plan = await billing_controller.get_hospital_plan(request.hospital_id)
#         if not hospital_plan:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail="Hospital plan not found"
#             )
        
#         if hospital_plan.status != PlanStatus.ACTIVE:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Cannot update services for plan with status: {hospital_plan.status}"
#             )
            
#         # Update services
#         result = await billing_controller.select_services(
#             request=request, 
#             user_id=current_user.user_id
#         )
#         return result
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=str(e)
#         )


# ────────────────────────────────────────────────────────────────────────────────
#  New endpoint: Get current subscription / plan details
# ────────────────────────────────────────────────────────────────────────────────


# @router.get(
#     "/plan/current",
#     response_model=Union[HospitalPlanResponse, IndividualPlanResponse],
#     summary="Get current subscription details"
# )
# async def get_current_plan(
#     role_entity_id: str = Query(None, alias="entity_id", description="Hospital or Individual ID (admin only)"),
#     current_user = Depends(jwt_auth.get_current_user)
# ):
#     """Return the active subscription / plan details for the caller.

#     Behaviour:
#     • Individual users → their own plan
#     • Hospital admins  → their hospital plan
#     • Platform admins  → must specify `hospital_id` **or** `individual_id` to fetch that entity's plan
#     """

#     # Individual user → own plan
#     if current_user.role == UserRole.INDIVIDUAL:
#         plan = await billing_controller.get_individual_plan(current_user.role_entity_id)
#         if plan is None:
#             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
#         return plan

#     # Hospital admin → hospital plan
#     if current_user.role == UserRole.HOSPITAL:
#         plan = await billing_controller.get_hospital_plan(current_user.role_entity_id)
#         if plan is None:  # function actually raises, but just in case
#             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
#         return plan

#     # Platform admin can fetch any entity's plan via a single identifier
#     if current_user.role == UserRole.ADMIN:
#         if not role_entity_id:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Admin must provide entity_id (hospital or individual)"
#             )

#         # Try hospital first
#         try:
#             plan = await billing_controller.get_hospital_plan(role_entity_id)
#             if plan is not None:
#                 return plan
#         except HTTPException as e:
#             if e.status_code != status.HTTP_404_NOT_FOUND:
#                 raise

#         # Fallback to individual
#         plan_ind = await billing_controller.get_individual_plan(role_entity_id)
#         if plan_ind is not None:
#             return plan_ind
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No plan found for the provided entity_id")

#     # Unsupported roles (assistants etc.)
#     raise HTTPException(
#         status_code=status.HTTP_403_FORBIDDEN,
#         detail="Insufficient permissions to view plan details"
#     )


@router.post("/plan/select", response_model=None)
async def select_plan(
    request: PlanSelectionRequest,
    current_user = Depends(jwt_auth.get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token")
):
    """
    Admin override: set an individual's plan manually.

    Rationale: This endpoint is restricted to ADMIN to avoid normal clients
    bypassing Stripe payment flows. Use only for support/tooling.
    """

    # Enforce ADMIN only
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can modify plans directly")

    # Validate plan type
    if request.plan_type not in [PlanType.ONE_MONTH, PlanType.THREE_MONTHS, PlanType.SIX_MONTHS]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan type. Choose one_month, three_months, or six_months")

    # Require explicit individual id in request.id
    if not request.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin must provide target individual id in 'id'")

    resp = await billing_controller.select_individual_plan(
        individual_id=request.id,
        plan_type=request.plan_type,
        user_id=current_user.user_id,
    )
    return resp

