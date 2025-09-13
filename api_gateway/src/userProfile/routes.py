from fastapi import APIRouter, HTTPException, status
from datetime import datetime
from .controller import UserProfileController
from .schema import (
    CreateUserProfileRequest, 
    UpdateUserProfileRequest, 
    UserProfileResponse, 
    UserProfileListResponse,
    UpdateEmotionalGoalRequest,
    UpdateAccountabilityGoalRequest,
    UpdateAnxietyGoalRequest,
    UpdateTherapyGoalRequest,
    UpdateLonelinessGoalRequest
)
from typing import Dict, Any, List

router = APIRouter(prefix="/user-profile", tags=["User Profile"])
profile_controller = UserProfileController()


@router.post("/{role_entity_id}", response_model=Dict[str, Any])
async def create_user_profile(
    role_entity_id: str,
    request: CreateUserProfileRequest,
):
    """Create a new user profile for a user (identified by role_entity_id)"""
    
    profile_data = request.dict(exclude_unset=True)
    return await profile_controller.create_user_profile(role_entity_id, profile_data)


@router.get("/{role_entity_id}", response_model=UserProfileListResponse)
async def get_all_user_profiles(
    role_entity_id: str,
):
    """Get all user profiles for a user (identified by role_entity_id)"""
    
    profiles = await profile_controller.get_all_user_profiles(role_entity_id)
    return UserProfileListResponse(
        profiles=[UserProfileResponse(**profile) for profile in profiles],
        total_count=len(profiles),
        updated_at=datetime.utcnow()
    )


@router.get("/{role_entity_id}/{user_profile_id}", response_model=UserProfileResponse)
async def get_user_profile(
    role_entity_id: str,
    user_profile_id: str,
):
    """Get a specific user profile by role_entity_id and user_profile_id"""
    
    profile = await profile_controller.get_user_profile(role_entity_id, user_profile_id)
    return UserProfileResponse(**profile)


@router.put("/{role_entity_id}/{user_profile_id}", response_model=Dict[str, Any])
async def update_user_profile(
    role_entity_id: str,
    user_profile_id: str,
    request: UpdateUserProfileRequest,
):
    """Update a specific user profile"""
    
    update_data = request.dict(exclude_unset=True, exclude_none=True)
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No data provided for update"
        )
    
    return await profile_controller.update_user_profile(role_entity_id, user_profile_id, update_data)


@router.delete("/{role_entity_id}/{user_profile_id}", response_model=Dict[str, Any])
async def delete_user_profile(
    role_entity_id: str,
    user_profile_id: str,
):
    """Delete a specific user profile"""
    
    return await profile_controller.delete_user_profile(role_entity_id, user_profile_id)


# ---------- Goal Update Endpoints ----------

@router.put("/goals/emotional/{user_profile_id}", response_model=Dict[str, Any])
async def update_emotional_goal(
    user_profile_id: str,
    request: UpdateEmotionalGoalRequest,
):
    """Update or create emotional companion agent goal for a user profile"""
    
    update_data = request.dict(exclude_unset=True, exclude_none=True)
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No data provided for update"
        )
    
    return await profile_controller.update_emotional_goal(user_profile_id, update_data)


@router.put("/goals/accountability/{user_profile_id}", response_model=Dict[str, Any])
async def update_accountability_goal(
    user_profile_id: str,
    request: UpdateAccountabilityGoalRequest,
):
    """Update or create accountability agent goal for a user profile"""
    
    update_data = request.dict(exclude_unset=True, exclude_none=True)
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No data provided for update"
        )
    
    return await profile_controller.update_accountability_goal(user_profile_id, update_data)


@router.put("/goals/anxiety/{user_profile_id}", response_model=Dict[str, Any])
async def update_anxiety_goal(
    user_profile_id: str,
    request: UpdateAnxietyGoalRequest,
):
    """Update or create social anxiety agent goal for a user profile"""
    
    update_data = request.dict(exclude_unset=True, exclude_none=True)
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No data provided for update"
        )
    
    return await profile_controller.update_anxiety_goal(user_profile_id, update_data)


@router.put("/goals/therapy/{user_profile_id}", response_model=Dict[str, Any])
async def update_therapy_goal(
    user_profile_id: str,
    request: UpdateTherapyGoalRequest,
):
    """Update or create therapy agent goal for a user profile"""
    
    update_data = request.dict(exclude_unset=True, exclude_none=True)
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No data provided for update"
        )
    
    return await profile_controller.update_therapy_goal(user_profile_id, update_data)


@router.put("/goals/loneliness/{user_profile_id}", response_model=Dict[str, Any])
async def update_loneliness_goal(
    user_profile_id: str,
    request: UpdateLonelinessGoalRequest,
):
    """Update or create loneliness agent goal for a user profile"""
    
    update_data = request.dict(exclude_unset=True, exclude_none=True)
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No data provided for update"
        )
    
    return await profile_controller.update_loneliness_goal(user_profile_id, update_data)


# ---------- Goal Fetch Endpoints ----------

@router.get("/goals/{role_entity_id}/emotional", response_model=List[Dict[str, Any]])
async def get_emotional_goals(
    role_entity_id: str,
):
    """Get all emotional companion goals for a user"""
    
    return await profile_controller.get_emotional_goals(role_entity_id)


@router.get("/goals/{role_entity_id}/accountability", response_model=List[Dict[str, Any]])
async def get_accountability_goals(
    role_entity_id: str,
):
    """Get all accountability goals for a user"""
    
    return await profile_controller.get_accountability_goals(role_entity_id)


@router.get("/goals/{role_entity_id}/anxiety", response_model=List[Dict[str, Any]])
async def get_anxiety_goals(
    role_entity_id: str,
):
    """Get all social anxiety goals for a user"""
    
    return await profile_controller.get_anxiety_goals(role_entity_id)


@router.get("/goals/{role_entity_id}/therapy", response_model=List[Dict[str, Any]])
async def get_therapy_goals(
    role_entity_id: str,
):
    """Get all therapy goals for a user"""
    
    return await profile_controller.get_therapy_goals(role_entity_id)


@router.get("/goals/{role_entity_id}/loneliness", response_model=List[Dict[str, Any]])
async def get_loneliness_goals(
    role_entity_id: str,
):
    """Get all loneliness goals for a user"""
    
    return await profile_controller.get_loneliness_goals(role_entity_id)
