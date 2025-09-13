from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Dict, Any, Optional
from datetime import datetime

from .controller import PatientController
from .schema import Patient, Visit, PatientStatus, VisitStatus
from ...middlewares.jwt_auth import JWTAuthController

patient_router = APIRouter(prefix="/patients", tags=["Patients"])
jwt_auth = JWTAuthController()

def get_patient_controller():
    return PatientController()

@patient_router.get("/", response_model=List[Patient])
async def list_patients(
    owner_id: Optional[str] = Query(None, description="Filter by owner ID"),
    status: Optional[str] = Query(None, description="Filter by patient status"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=100, description="Maximum number of records to return"),
    controller: PatientController = Depends(get_patient_controller),
    current_user = Depends(jwt_auth.get_current_user)
):
    """
    List patients with optional filtering
    
    This endpoint:
    - Returns a list of patients
    - Can be filtered by owner ID and status
    - Supports pagination with skip and limit parameters
    """
    # Check if user has access to these patients
    if current_user.role == "individual":
        # Individual users can only see their own patients
        owner_id = current_user.role_entity_id
    
    return await controller.list_patients(owner_id, status, skip, limit)

@patient_router.get("/{patient_id}", response_model=Patient)
async def get_patient(
    patient_id: str,
    controller: PatientController = Depends(get_patient_controller),
    current_user = Depends(jwt_auth.get_current_user)
):
    """
    Get a patient by ID
    
    This endpoint:
    - Returns a patient by ID
    - Includes all patient data including visits
    """
    patient = await controller.get_patient(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    
    # Check if user has access to this patient
    if current_user.role == "individual" and patient.owner_id != current_user.role_entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this patient"
        )
    
    return patient

@patient_router.post("/", response_model=Patient)
async def create_patient(
    patient_data: Dict[str, Any],
    controller: PatientController = Depends(get_patient_controller),
    current_user = Depends(jwt_auth.get_current_user)
):
    """
    Create a new patient
    
    This endpoint:
    - Creates a new patient record
    - Sets the owner based on the current user
    """
    # Set owner based on current user
    if current_user.role == "individual":
        patient_data["owner_type"] = "individual"
        patient_data["owner_id"] = current_user.role_entity_id
    elif current_user.role in ["hospital", "assistant"]:
        patient_data["owner_type"] = "organization"
        patient_data["owner_id"] = current_user.role_entity_id
    
    return await controller.create_patient(patient_data)

@patient_router.put("/{patient_id}", response_model=Patient)
async def update_patient(
    patient_id: str,
    update_data: Dict[str, Any],
    controller: PatientController = Depends(get_patient_controller),
    current_user = Depends(jwt_auth.get_current_user)
):
    """
    Update a patient
    
    This endpoint:
    - Updates a patient record
    - Returns the updated patient
    """
    # Check if patient exists and user has access
    patient = await controller.get_patient(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    
    # Check if user has access to this patient
    if current_user.role == "individual" and patient.owner_id != current_user.role_entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this patient"
        )
    
    # Update audit trail
    update_data["last_modified_by"] = current_user.user_id
    update_data["last_modified_at"] = datetime.utcnow()
    
    # Perform update
    updated_patient = await controller.update_patient(patient_id, update_data)
    if not updated_patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    
    return updated_patient

@patient_router.delete("/{patient_id}")
async def delete_patient(
    patient_id: str,
    controller: PatientController = Depends(get_patient_controller),
    current_user = Depends(jwt_auth.get_current_user)
):
    """
    Delete a patient (soft delete)
    
    This endpoint:
    - Soft deletes a patient by changing status to ARCHIVED
    - Returns success message
    """
    # Check if patient exists and user has access
    patient = await controller.get_patient(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    
    # Check if user has access to this patient
    if current_user.role == "individual" and patient.owner_id != current_user.role_entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this patient"
        )
    
    # Perform delete
    success = await controller.delete_patient(patient_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete patient"
        )
    
    return {"message": "Patient deleted successfully"}

@patient_router.post("/{patient_id}/visits", response_model=Patient)
async def add_visit(
    patient_id: str,
    visit_data: Dict[str, Any],
    controller: PatientController = Depends(get_patient_controller),
    current_user = Depends(jwt_auth.get_current_user)
):
    """
    Add a visit to a patient
    
    This endpoint:
    - Adds a new visit to a patient
    - Returns the updated patient with the new visit
    """
    # Check if patient exists and user has access
    patient = await controller.get_patient(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    
    # Check if user has access to this patient
    if current_user.role == "individual" and patient.owner_id != current_user.role_entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this patient"
        )
    
    # Add visit
    updated_patient = await controller.add_visit(patient_id, visit_data)
    if not updated_patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    
    return updated_patient

@patient_router.put("/{patient_id}/visits/{visit_id}", response_model=Patient)
async def update_visit(
    patient_id: str,
    visit_id: str,
    update_data: Dict[str, Any],
    controller: PatientController = Depends(get_patient_controller),
    current_user = Depends(jwt_auth.get_current_user)
):
    """
    Update a visit
    
    This endpoint:
    - Updates a specific visit for a patient
    - Returns the updated patient with the modified visit
    """
    # Check if patient exists and user has access
    patient = await controller.get_patient(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
        )
    
    # Check if user has access to this patient
    if current_user.role == "individual" and patient.owner_id != current_user.role_entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this patient"
        )
    
    # Update visit
    updated_patient = await controller.update_visit(patient_id, visit_id, update_data)
    if not updated_patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient or visit not found"
        )
    
    return updated_patient 
