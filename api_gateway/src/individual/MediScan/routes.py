from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from typing import List, Dict, Any, Optional
import os
from ....middlewares.jwt_auth import JWTAuthController
from ...auth.schema import UserRole, JWTClaims
from .ocr_controller import OCRController
from .schema import OCRJobResponse, OCRJobListResponse, OCRResultResponse
from ...patients.controller import PatientController
from .controller import PatientInteractioController
from ...patients.schema import Patient
# Create router
router = APIRouter(prefix="/individual/mediscan", tags=["MediScan"])

# Initialize controllers
jwt_auth = JWTAuthController()

patient_controller = PatientController()
patient_interactio_controller = PatientInteractioController()

def get_ocr_controller():
    """Get OCR controller instance"""
    return OCRController()

def check_individual_access(user: JWTClaims):
    """Check if user has individual role access"""
    if user.role != UserRole.INDIVIDUAL:
        print("here is error")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only individual users can access MediScan features"
        )
    return user

@router.post("/ocr")
async def process_document_ocr(
    file: UploadFile = File(...),
    patient_id: Optional[str] = Form(None),
    controller: OCRController = Depends(get_ocr_controller),
    current_user: JWTClaims = Depends(jwt_auth.get_current_user)
):
    """
    Process a document with OCR
    
    This endpoint:
    - Accepts PDF, JPG, PNG, TIFF, HEIC files
    - Uses Google Cloud Vision API for OCR
    - Returns the extracted text
    
    Only individual users can access this endpoint.
    """
    # Check if user has individual role
    print("hitting")
    check_individual_access(current_user)
    
    # Use role_entity_id (the individual's account id) as owner_id so the patient is linked correctly
    result = await controller.process_document(file, current_user.role_entity_id, patient_id)
    
    return result

@router.get("/ocr/{job_id}", response_model=OCRJobResponse)
async def get_ocr_job(
    job_id: str,
    controller: OCRController = Depends(get_ocr_controller),
    current_user: JWTClaims = Depends(jwt_auth.get_current_user)
):
    """
    Get OCR job status and result
    
    This endpoint:
    - Returns the status of an OCR job
    - If completed, returns the extracted text
    
    Only individual users can access this endpoint.
    """
    # Check if user has individual role
    check_individual_access(current_user)
    
    # Get job
    result = await controller.get_ocr_job(job_id, current_user.user_id)
    
    return result

@router.get("/ocr", response_model=OCRJobListResponse)
async def get_ocr_jobs(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    controller: OCRController = Depends(get_ocr_controller),
    current_user: JWTClaims = Depends(jwt_auth.get_current_user)
):
    """
    Get all OCR jobs for the current user
    
    This endpoint:
    - Returns a paginated list of OCR jobs
    - Includes job status and metadata
    
    Only individual users can access this endpoint.
    """
    # Check if user has individual role
    
    check_individual_access(current_user)
    
    # Calculate offset
    offset = (page - 1) * per_page
    
    # Get jobs
    jobs = await controller.get_user_jobs(
        current_user.user_id,
        limit=per_page,
        offset=offset
    )
    
    # Get total count (for pagination)
    total = len(jobs)  # This should be replaced with a proper count query
    
    return {
        "jobs": jobs,
        "total": total,
        "page": page,
        "per_page": per_page
    }

@router.get("/debug/credentials")
async def debug_credentials(
    controller: OCRController = Depends(get_ocr_controller),
    current_user: JWTClaims = Depends(jwt_auth.get_current_user)
):
    """
    Debug endpoint to check credentials path
    """
    # Check if user has individual role
    check_individual_access(current_user)
    
    # Path to credentials file
    credentials_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
        "keys",
        "google-cloudvision-credentials.json"
    )
    
    # Check if file exists
    exists = os.path.exists(credentials_path)
    
    return {
        "credentials_path": credentials_path,
        "exists": exists,
        "cwd": os.getcwd(),
        "client_initialized": controller.vision_client is not None
    }

@router.get("/patient/{patient_id}/documents")
async def list_patient_documents(
    patient_id: str,
    controller: PatientController = Depends(lambda: patient_controller),
    current_user: JWTClaims = Depends(jwt_auth.get_current_user)
):
    """List visits/documents for a patient (individual owner only)"""
    check_individual_access(current_user)

    patient = await controller.get_patient(patient_id)
    if not patient or patient.owner_id != current_user.role_entity_id:
        raise HTTPException(status_code=404, detail="Patient not found or access denied")

    return {"documents": patient.visits}


@router.delete("/patient/{patient_id}/documents/{visit_id}")
async def delete_patient_document(
    patient_id: str,
    visit_id: str,
    controller: PatientController = Depends(lambda: patient_controller),
    current_user: JWTClaims = Depends(jwt_auth.get_current_user)
):
    """Delete a document (visit) from patient"""
    check_individual_access(current_user)

    # Ensure ownership
    patient = await controller.get_patient(patient_id)
    if not patient or patient.owner_id != current_user.role_entity_id:
        raise HTTPException(status_code=404, detail="Patient not found or access denied")

    success = await controller.delete_visit(patient_id, visit_id)
    if not success:
        raise HTTPException(status_code=404, detail="Visit not found")

    return {"message": "Document deleted"}


# ---------------- Update document (visit) ----------------

@router.put("/patient/{patient_id}/documents/{visit_id}")
async def update_patient_document(
    patient_id: str,
    visit_id: str,
    update_data: Dict[str, Any],
    controller: PatientController = Depends(lambda: patient_controller),
    current_user: JWTClaims = Depends(jwt_auth.get_current_user)
):
    """Update a document (visit) for a patient"""
    check_individual_access(current_user)

    patient = await controller.get_patient(patient_id)
    if not patient or patient.owner_id != current_user.role_entity_id:
        raise HTTPException(status_code=404, detail="Patient not found or access denied")

    updated_patient = await controller.update_visit(patient_id, visit_id, update_data)
    if not updated_patient:
        raise HTTPException(status_code=404, detail="Visit not found or update failed")

    return {"message": "Document updated", "patient": updated_patient}






# ---------------- Patients interaction routes----------------



@router.get("/patients", response_model=List[Patient])
async def get_patients(
    current_user: JWTClaims = Depends(jwt_auth.get_current_user)
):
    """
    Get all patients for the authenticated individual user
    """
    check_individual_access(current_user)
    patients = await patient_interactio_controller.get_patients_by_owner_id(current_user.role_entity_id)
    return patients
