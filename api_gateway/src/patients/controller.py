from fastapi import HTTPException, status
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

from .schema import Patient, PatientStatus, Visit, VisitStatus
from api_gateway.database.db import get_database

class PatientController:
    """Controller for patient management"""

    def __init__(self):
        self.db = get_database()
        self.patients_collection = self.db.patients
        self._create_indexes()
    
    def _create_indexes(self):
        """Create necessary database indexes"""
        from pymongo import errors
        try:
            # Ensure all existing docs have a non-null unique patient_id before creating the unique index
            bulk_ops = []
            from pymongo import UpdateOne
            cursor = self.patients_collection.find(
                {"$or": [{"patient_id": {"$exists": False}}, {"patient_id": None}]},
                {"_id": 1},
            )
            for doc in cursor:
                bulk_ops.append(
                    UpdateOne(
                        {"_id": doc["_id"]},
                        {"$set": {"patient_id": f"patient-{uuid.uuid4()}"}},
                        upsert=False,
                    )
                )

            if bulk_ops:
                self.patients_collection.bulk_write(bulk_ops)

            # Create indexes (sparse to ignore docs without patient_id just in case)
            self.patients_collection.create_index("patient_id", unique=True, sparse=True)
            self.patients_collection.create_index("owner_id")
            self.patients_collection.create_index("name")
            self.patients_collection.create_index("medical_record_number")
            self.patients_collection.create_index("status")
        except errors.DuplicateKeyError as dup_err:
            # Log and continue without crashing server
            print(f"[Patients] Duplicate key error while creating index: {dup_err}")
        except Exception as e:
            print(f"Error creating indexes: {str(e)}")
    
    async def create_patient(self, patient_data: Dict[str, Any]) -> Patient:
        """Create a new patient record"""
        # Generate unique ID if not provided
        if "patient_id" not in patient_data:
            patient_data["patient_id"] = f"patient-{uuid.uuid4()}"
        
        # Set timestamps
        current_time = datetime.utcnow()
        patient_data["created_at"] = current_time
        patient_data["updated_at"] = current_time
        
        # Create patient object
        patient = Patient(**patient_data)
        print(patient)
        
        # Insert into database
        # Convert to BSON-friendly types (e.g. Enums → value, datetime → ISO strings)
        from fastapi.encoders import jsonable_encoder
        self.patients_collection.insert_one(jsonable_encoder(patient))
        
        return patient
    
    async def get_patient(self, patient_id: str) -> Optional[Patient]:
        """Get a patient by ID"""
        patient_data = self.patients_collection.find_one({"patient_id": patient_id})
        if not patient_data:
            return None
        
        # Convert MongoDB _id to string
        if "_id" in patient_data:
            patient_data["_id"] = str(patient_data["_id"])
        
        return Patient(**patient_data)
    
    async def update_patient(self, patient_id: str, update_data: Dict[str, Any]) -> Optional[Patient]:
        """Update a patient record"""
        # Get existing patient
        existing_patient = await self.get_patient(patient_id)
        if not existing_patient:
            return None
        
        # Update timestamps
        update_data["updated_at"] = datetime.utcnow()
        
        # Update in database
        self.patients_collection.update_one(
            {"patient_id": patient_id},
            {"$set": update_data}
        )
        
        # Get updated patient
        return await self.get_patient(patient_id)
    
    async def delete_patient(self, patient_id: str) -> bool:
        """Delete a patient (soft delete by changing status)"""
        result = self.patients_collection.update_one(
            {"patient_id": patient_id},
            {
                "$set": {
                    "status": PatientStatus.ARCHIVED.value,
                    "is_active": False,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
    
    async def list_patients(self, owner_id: Optional[str] = None, status: Optional[str] = None, 
                           skip: int = 0, limit: int = 100) -> List[Patient]:
        """List patients with optional filtering"""
        # Build query
        query = {}
        if owner_id:
            query["owner_id"] = owner_id
        if status:
            query["status"] = status
        else:
            query["is_active"] = True  # Default to active patients
        
        # Execute query
        cursor = self.patients_collection.find(query).skip(skip).limit(limit)
        
        # Convert to Patient objects
        patients = []
        for patient_data in cursor:
            # Convert MongoDB _id to string
            if "_id" in patient_data:
                patient_data["_id"] = str(patient_data["_id"])
            
            patients.append(Patient(**patient_data))
        
        return patients
    
    async def add_visit(self, patient_id: str, visit_data: Dict[str, Any]) -> Optional[Patient]:
        """Add a visit to a patient"""
        # Get existing patient
        existing_patient = await self.get_patient(patient_id)
        if not existing_patient:
            return None
        
        # Generate visit ID if not provided
        if "patient_id" not in visit_data:
            visit_data["patient_id"] = f"visit-{uuid.uuid4()}"
        
        # Set timestamps
        current_time = datetime.utcnow()
        visit_data["created_at"] = current_time
        visit_data["updated_at"] = current_time
        
        # Create visit object
        visit = Visit(**visit_data)
        
        # Update patient with new visit
        self.patients_collection.update_one(
            {"patient_id": patient_id},
            {
                "$push": {"visits": visit.dict()},
                "$set": {
                    "updated_at": current_time,
                    "last_visit": current_time,
                    "visit_status": visit.status
                }
            }
        )
        
        # Get updated patient
        return await self.get_patient(patient_id)
    
    async def update_visit(self, patient_id: str, visit_id: str, 
                          update_data: Dict[str, Any]) -> Optional[Patient]:
        """Update a specific visit for a patient"""
        # Get existing patient
        existing_patient = await self.get_patient(patient_id)
        if not existing_patient:
            return None
        
        # Find the visit index
        visit_index = None
        for i, visit in enumerate(existing_patient.visits):
            if visit.patient_id == visit_id:
                visit_index = i
                break
        
        if visit_index is None:
            return None
        
        # Update timestamp
        update_data["updated_at"] = datetime.utcnow()
        
        # Update the visit in the patient document
        update_field = {f"visits.{visit_index}.{key}": value for key, value in update_data.items()}
        
        self.patients_collection.update_one(
            {"patient_id": patient_id},
            {
                "$set": {
                    **update_field,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Get updated patient
        return await self.get_patient(patient_id) 
    
    async def delete_visit(self, patient_id: str, visit_id: str) -> bool:
        """Delete a visit from a patient"""
        try:
            result = self.db.patients.update_one(
                {"patient_id": patient_id},
                {"$pull": {"visits": {"patient_id": visit_id}}, "$set": {"updated_at": datetime.utcnow()}}
            )
            return result.modified_count > 0
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error deleting visit: {e}") 
