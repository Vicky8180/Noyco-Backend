


from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from typing import List, Optional
from .controller import FHIRCSVProcessor
from .fetchController import FHIRDataFetcher
from .schema import (
    CSVMappingRequest, MappingTemplateRequest, ProcessingResponse,
    FHIRConversionStatus, MappingTemplate, FHIRResourceType
)
from datetime import datetime
import io
import pandas as pd
import json
import io
import pandas as pd

router = APIRouter(prefix="/api/fhir", tags=["FHIR Processing"])
processor = FHIRCSVProcessor()
fetcher = FHIRDataFetcher()

# Existing endpoints...

@router.post("/upload-csv", response_model=ProcessingResponse)
async def upload_csv_file(
    file: UploadFile = File(...),
    role_entity_id: str = Form(...),
    file_name: str = Form(...),
    all_mappings: str = Form(...)
):
    """
    Upload CSV file and process it with field mappings for all resource types
    """
    try:
        import json
        mappings_by_resource = json.loads(all_mappings)
        print(f"Received file: {file.filename}, Role Entity ID: {role_entity_id}")
        print(f"All mappings: {mappings_by_resource}")

        # Read CSV file once
        content = await file.read()
        df = pd.read_csv(io.StringIO(content.decode('utf-8')))
        df.columns = df.columns.str.strip()

        # Generate unique upload_id
        upload_id = f"{file.filename}_{role_entity_id}_{pd.Timestamp.now().value}"
        
        # Process all resources with proper relationships
        result = await processor.process_all_resources_with_relationships(
            df=df,
            mappings_by_resource=mappings_by_resource,
            upload_id=upload_id,
            role_entity_id=role_entity_id,
            file_name=file_name
        )
        
        return ProcessingResponse(
            upload_id=upload_id,
            status="completed",
            message=result["message"]
        )
        
    except Exception as e:
        print(f"Error in upload_csv_file: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/conversions/{role_entity_id}")
async def get_conversions(role_entity_id: str):
    """Get all conversions for a role entity"""
    try:
        conversions = await processor.get_conversions_by_role_entity(role_entity_id)
        return {"conversions": conversions, "total": len(conversions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resources/{role_entity_id}")
async def get_fhir_resources(
    role_entity_id: str,
    resource_type: Optional[str] = None,
    patient_key: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
):
    """Get FHIR resources with optional filtering"""
    try:
        resources = await processor.get_fhir_resources(
            role_entity_id=role_entity_id,
            resource_type=resource_type,
            patient_key=patient_key,
            limit=limit,
            skip=skip
        )
        return {"resources": resources, "total": len(resources)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patient-complete/{patient_key}")
async def get_patient_complete_data(patient_key: str, role_entity_id: str):
    """Get complete patient data including all related resources"""
    try:
        complete_data = await processor.get_patient_complete_data(patient_key, role_entity_id)
        return complete_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mapping-template", response_model=str)
async def save_mapping_template(request: MappingTemplateRequest):
    """Save mapping template"""
    try:
        template_id = await processor.save_mapping_template(request)
        return template_id
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mapping-templates/{role_entity_id}")
async def get_mapping_templates(role_entity_id: str):
    """Get mapping templates for role entity"""
    try:
        templates = await processor.get_mapping_templates(role_entity_id)
        return {"templates": templates}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# New endpoints for the frontend dashboard
@router.get("/patients")
async def get_all_patients(
    role_entity_id: str,
    limit: int = 100,
    skip: int = 0,
    search: Optional[str] = None
):
    """Get all patients with optional search filtering"""
    try:
        patients = await fetcher.get_all_patients(
            role_entity_id=role_entity_id,
            limit=limit,
            skip=skip,
            search=search
        )
        return {"patients": patients, "total": len(patients)}
    except Exception as e:
        print(f"Error in get_all_patients: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/patients/{patient_id}")
async def get_patient_by_id(patient_id: str, role_entity_id: str):
    """Get a single patient by ID"""
    try:
        patient = await fetcher.get_patient_by_id(patient_id, role_entity_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        return patient
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_patient_by_id: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/patients/{patient_id}/conditions")
async def get_patient_conditions(patient_id: str, role_entity_id: str):
    """Get conditions for a specific patient"""
    try:
        conditions = await fetcher.get_patient_conditions(patient_id, role_entity_id)
        return conditions
    except Exception as e:
        print(f"Error in get_patient_conditions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/patients/{patient_id}/observations")
async def get_patient_observations(patient_id: str, role_entity_id: str):
    """Get observations for a specific patient"""
    try:
        observations = await fetcher.get_patient_observations(patient_id, role_entity_id)
        return observations
    except Exception as e:
        print(f"Error in get_patient_observations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/patients/{patient_id}/encounters")
async def get_patient_encounters(patient_id: str, role_entity_id: str):
    """Get encounters for a specific patient"""
    try:
        encounters = await fetcher.get_patient_encounters(patient_id, role_entity_id)
        return encounters
    except Exception as e:
        print(f"Error in get_patient_encounters: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/patients/{patient_id}/procedures")
async def get_patient_procedures(patient_id: str, role_entity_id: str):
    """Get procedures for a specific patient"""
    try:
        procedures = await fetcher.get_patient_procedures(patient_id, role_entity_id)
        return procedures
    except Exception as e:
        print(f"Error in get_patient_procedures: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/patients/{patient_id}/full-data")
async def get_patient_full_data(patient_id: str, role_entity_id: str):
    """Get all data for a specific patient (single API call for all resources)"""
    try:
        full_data = await fetcher.get_patient_full_data(patient_id, role_entity_id)
        return full_data
    except Exception as e:
        print(f"Error in get_patient_full_data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/patients/stats/{role_entity_id}")
async def get_patients_statistics(role_entity_id: str):
    """Get statistics about patients for a role entity"""
    try:
        stats = await fetcher.get_patients_statistics(role_entity_id)
        return stats
    except Exception as e:
        print(f"Error in get_patients_statistics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/patients/search")
async def search_patients(
    role_entity_id: str, 
    query: str,
    field: Optional[str] = None,
    operator: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
):
    """Advanced search for patients"""
    try:
        patients = await fetcher.search_patients(
            role_entity_id=role_entity_id,
            query=query,
            field=field,
            operator=operator,
            limit=limit,
            skip=skip
        )
        return {"patients": patients, "total": len(patients)}
    except Exception as e:
        print(f"Error in search_patients: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
