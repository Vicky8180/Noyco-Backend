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


@router.get("/plan", response_model=AvailablePlansResponse)
async def get_available_plans(
    current_user = Depends(jwt_auth.get_current_user)
):
    """
    Get available plans based on user role.

    Returns different plan options based on the user's role:
    - For hospitals: LITE and PRO plans
    - For individuals: HOBBY and BASIC plans
    - For admins: All plans
    
    Also includes the user's current plan if they have one.
    """
    return await billing_controller.get_available_plans(
        user_role=current_user.role,
        role_entity_id=current_user.role_entity_id
    )



@router.get("/services", response_model=AvailableServicesResponse)
async def get_available_services(
    current_user = Depends(jwt_auth.get_current_user)
):
    """Get available services based on the user's current plan"""
    try:
        # Get available services
        role_entity_id = None
        
        # For hospitals and assistants (linked to hospitals), get the hospital's services
        if current_user.role == UserRole.HOSPITAL:
            role_entity_id = current_user.role_entity_id
        elif current_user.role == UserRole.ASSISTANT:
            # Assistant belongs to a hospital
            assistant = await billing_controller.get_assistant_by_id(current_user.role_entity_id)
            if assistant:
                role_entity_id = assistant.get("hospital_id")
        
        services = await billing_controller.get_available_services(
            user_id=current_user.user_id, 
            role_entity_id=role_entity_id
        )
        return services
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    Select a plan for a hospital **or** an individual.
    - Hospitals can choose LITE / PRO
    - Individuals can choose LITE / PRO
    """

    # INDIVIDUAL FLOW -----------------------------------------------------
    if current_user.role == UserRole.INDIVIDUAL:
        # Individuals can now choose the same core plans as hospitals (LITE / PRO)
        if request.plan_type not in [PlanType.LITE, PlanType.PRO]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Individuals can only choose LITE or PRO plans"
            )
        # id is not strictly needed but frontend sends it ‑ double-check
        if request.id and request.id != current_user.role_entity_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only manage your own plan"
            )
        # Delegate to controller helper so DB is updated properly
        resp = await billing_controller.select_individual_plan(
            individual_id=current_user.role_entity_id,
            plan_type=request.plan_type,
            user_id=current_user.user_id,
        )
        return resp

    # HOSPITAL / ADMIN FLOW ----------------------------------------------
    if current_user.role not in [UserRole.ADMIN, UserRole.HOSPITAL]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only hospital admins, individuals or platform admins can select plans"
        )

    # Hospital admins can only manage their own hospital
    if current_user.role == UserRole.HOSPITAL:
        hospital = await billing_controller.get_hospital_by_id(current_user.role_entity_id)
        if not hospital or hospital.get("id") != request.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Hospital admins can only manage their own hospital plan"
            )

    return await billing_controller.select_plan(request, current_user.user_id)

