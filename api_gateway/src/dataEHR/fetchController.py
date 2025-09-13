
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
import uuid
from datetime import datetime
import re
from bson import ObjectId

from api_gateway.database.db import get_database


def serialize_document(doc):
    """Convert MongoDB document for JSON serialization"""
    if doc is None:
        return None
    
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = serialize_document(value)
            elif isinstance(value, list):
                result[key] = [serialize_document(item) for item in value]
            else:
                result[key] = value
        return result
    elif isinstance(doc, list):
        return [serialize_document(item) for item in doc]
    elif isinstance(doc, ObjectId):
        return str(doc)
    elif isinstance(doc, datetime):
        return doc.isoformat()
    else:
        return doc


class FHIRDataFetcher:
    """Handles retrieval of FHIR data for frontend applications"""

    def __init__(self):
        self.db = get_database()
        self.assistant_collection = self.db.assistants
        self.patient_collection = self.db.fhir_patient
        self.condition_collection = self.db.fhir_condition
        self.observation_collection = self.db.fhir_observation
        self.encounter_collection = self.db.fhir_encounter
        self.procedure_collection = self.db.fhir_procedure
        self.conversion_status_collection = self.db.fhir_conversion_status
        
        # Collection mapping for convenience
        self.resource_collections = {
            "Patient": self.patient_collection,
            "Condition": self.condition_collection,
            "Observation": self.observation_collection,
            "Encounter": self.encounter_collection,
            "Procedure": self.procedure_collection
        }

    async def _resolve_hospital_id(self, role_entity_id: str) -> str:
        """
        Resolve a hospital ID from a *role_entity_id*.

        The incoming *role_entity_id* could be either:
        1. A **hospital ID** (when the logged-in user is a hospital admin).
        2. An **assistant ID** (when the logged-in user is an assistant).

        Behaviour:
        • If the ID exists in the *hospitals* collection, we accept it directly.
        • Else, we attempt to treat it as an assistant ID and look up the parent hospital.
        • If neither look-up succeeds we raise 404.
        """

        # 1️⃣ Direct hospital lookup – most efficient path for hospital users
        hospital = self.db.hospitals.find_one({"id": role_entity_id})
        if hospital:
            return role_entity_id

        # 2️⃣ Assistant lookup
        assistant = self.assistant_collection.find_one({"id": role_entity_id})
        if not assistant:
            raise HTTPException(status_code=404, detail=f"Role entity {role_entity_id} not found")

        hospital_id = assistant.get("hospital_id")
        if not hospital_id:
            raise HTTPException(status_code=400, detail="No hospital associated with this assistant")

        return hospital_id

    async def get_all_patients(
        self, 
        role_entity_id: str, 
        limit: int = 100, 
        skip: int = 0, 
        search: Optional[str] = None
    ) -> List[Dict]:
        """
        Get all patients for a role entity with optional search filtering
        """
        # Resolve hospital_id from role_entity_id (assistant ID)
        hospital_id = await self._resolve_hospital_id(role_entity_id)
        
        query = {"role_entity_id": hospital_id}
        
        # Add text search if provided
        if search and search.strip():
            # Create regex search pattern (case insensitive)
            search_pattern = re.compile(f".*{re.escape(search.strip())}.*", re.IGNORECASE)
            
            # Search in multiple fields
            query["$or"] = [
                {"id": {"$regex": search_pattern}},
                {"name.given": {"$regex": search_pattern}},
                {"name.family": {"$regex": search_pattern}},
                {"telecom.value": {"$regex": search_pattern}},
                {"address.line": {"$regex": search_pattern}},
                {"address.city": {"$regex": search_pattern}},
                {"address.state": {"$regex": search_pattern}},
                {"address.postalCode": {"$regex": search_pattern}},
                {"address.country": {"$regex": search_pattern}}
            ]
        
        # Execute query with pagination
        cursor = self.patient_collection.find(query).skip(skip).limit(limit)
        
        # Convert MongoDB cursor to list and serialize documents
        patients = list(cursor)
        return [serialize_document(patient) for patient in patients]

    async def get_patient_by_id(self, patient_id: str, role_entity_id: str) -> Optional[Dict]:
        """
        Get a single patient by ID
        """
        # Resolve hospital_id from role_entity_id (assistant ID)
        hospital_id = await self._resolve_hospital_id(role_entity_id)
        
        # Try direct ID match first
        patient = self.patient_collection.find_one({
            "id": patient_id,
            "role_entity_id": hospital_id
        })
        
        # If not found, try patient_key match
        if not patient:
            patient = self.patient_collection.find_one({
                "patient_key": patient_id,
                "role_entity_id": hospital_id
            })
        
        return serialize_document(patient)

    async def get_patient_conditions(self, patient_id: str, role_entity_id: str) -> List[Dict]:
        """
        Get conditions for a specific patient
        """
        # Resolve hospital_id from role_entity_id (assistant ID)
        hospital_id = await self._resolve_hospital_id(role_entity_id)
        
        # First, find the patient to get the patient_key
        patient = await self.get_patient_by_id(patient_id, role_entity_id)
        if not patient:
            return []
            
        patient_key = patient.get("patient_key") or patient.get("id")
        
        # Query conditions using patient_key
        conditions = list(self.condition_collection.find({
            "patient_key": patient_key,
            "role_entity_id": hospital_id
        }))
        
        # If no results, try using subject.reference
        if not conditions:
            conditions = list(self.condition_collection.find({
                "subject.reference": {"$regex": f".*{patient_id}.*"},
                "role_entity_id": hospital_id
            }))
        
        return [serialize_document(condition) for condition in conditions]

    async def get_patient_observations(self, patient_id: str, role_entity_id: str) -> List[Dict]:
        """
        Get observations for a specific patient
        """
        # Resolve hospital_id from role_entity_id (assistant ID)
        hospital_id = await self._resolve_hospital_id(role_entity_id)
        
        patient = await self.get_patient_by_id(patient_id, role_entity_id)
        if not patient:
            return []
            
        patient_key = patient.get("patient_key") or patient.get("id")
        
        observations = list(self.observation_collection.find({
            "patient_key": patient_key,
            "role_entity_id": hospital_id
        }))
        
        if not observations:
            observations = list(self.observation_collection.find({
                "subject.reference": {"$regex": f".*{patient_id}.*"},
                "role_entity_id": hospital_id
            }))
        
        return [serialize_document(observation) for observation in observations]

    async def get_patient_encounters(self, patient_id: str, role_entity_id: str) -> List[Dict]:
        """
        Get encounters for a specific patient
        """
        # Resolve hospital_id from role_entity_id (assistant ID)
        hospital_id = await self._resolve_hospital_id(role_entity_id)
        
        patient = await self.get_patient_by_id(patient_id, role_entity_id)
        if not patient:
            return []
            
        patient_key = patient.get("patient_key") or patient.get("id")
        
        encounters = list(self.encounter_collection.find({
            "patient_key": patient_key,
            "role_entity_id": hospital_id
        }))
        
        if not encounters:
            encounters = list(self.encounter_collection.find({
                "subject.reference": {"$regex": f".*{patient_id}.*"},
                "role_entity_id": hospital_id
            }))
        
        return [serialize_document(encounter) for encounter in encounters]

    async def get_patient_procedures(self, patient_id: str, role_entity_id: str) -> List[Dict]:
        """
        Get procedures for a specific patient
        """
        # Resolve hospital_id from role_entity_id (assistant ID)
        hospital_id = await self._resolve_hospital_id(role_entity_id)
        
        patient = await self.get_patient_by_id(patient_id, role_entity_id)
        if not patient:
            return []
            
        patient_key = patient.get("patient_key") or patient.get("id")
        
        procedures = list(self.procedure_collection.find({
            "patient_key": patient_key,
            "role_entity_id": hospital_id
        }))
        
        if not procedures:
            procedures = list(self.procedure_collection.find({
                "subject.reference": {"$regex": f".*{patient_id}.*"},
                "role_entity_id": hospital_id
            }))
        
        return [serialize_document(procedure) for procedure in procedures]

    async def get_patient_full_data(self, patient_id: str, role_entity_id: str) -> Dict[str, Any]:
        """
        Get all data for a specific patient (single API call for all resources)
        """
        # Resolve hospital_id from role_entity_id (assistant ID)
        hospital_id = await self._resolve_hospital_id(role_entity_id)
        
        # Parallel fetching for better performance
        patient = await self.get_patient_by_id(patient_id, role_entity_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        
        # Fetch all related resources concurrently
        conditions = await self.get_patient_conditions(patient_id, role_entity_id)
        observations = await self.get_patient_observations(patient_id, role_entity_id)
        encounters = await self.get_patient_encounters(patient_id, role_entity_id)
        procedures = await self.get_patient_procedures(patient_id, role_entity_id)
        
        # Return consolidated data
        return {
            "patient": patient,
            "conditions": conditions,
            "observations": observations,
            "encounters": encounters,
            "procedures": procedures
        }

    async def get_patients_statistics(self, role_entity_id: str) -> Dict[str, Any]:
        """
        Get statistics about patients for a role entity
        """
        # Resolve hospital_id from role_entity_id (assistant ID)
        hospital_id = await self._resolve_hospital_id(role_entity_id)
        
        # Count total patients
        total_patients = self.patient_collection.count_documents({"role_entity_id": hospital_id})
        
        # Count patients by gender
        gender_stats = {}
        genders = ["male", "female", "other", "unknown"]
        for gender in genders:
            if gender == "unknown":
                count = self.patient_collection.count_documents({
                    "role_entity_id": hospital_id,
                    "$or": [
                        {"gender": {"$exists": False}},
                        {"gender": None},
                        {"gender": ""}
                    ]
                })
            else:
                count = self.patient_collection.count_documents({
                    "role_entity_id": hospital_id,
                    "gender": {"$regex": f"^{gender}$", "$options": "i"}  # Case-insensitive exact match
                })
            gender_stats[gender] = count
        
        # Count resources per patient type
        resource_counts = {
            "conditions": self.condition_collection.count_documents({"role_entity_id": hospital_id}),
            "observations": self.observation_collection.count_documents({"role_entity_id": hospital_id}),
            "encounters": self.encounter_collection.count_documents({"role_entity_id": hospital_id}),
            "procedures": self.procedure_collection.count_documents({"role_entity_id": hospital_id})
        }
        
        # Calculate average resources per patient
        avg_resources = {}
        if total_patients > 0:
            for resource_type, count in resource_counts.items():
                avg_resources[resource_type] = round(count / total_patients, 2)
        
        return {
            "total_patients": total_patients,
            "gender_distribution": gender_stats,
            "resource_counts": resource_counts,
            "avg_resources_per_patient": avg_resources,
            "last_updated": datetime.utcnow().isoformat()
        }

    async def search_patients(
        self,
        role_entity_id: str,
        query: str,
        field: Optional[str] = None,
        operator: Optional[str] = None,
        limit: int = 100,
        skip: int = 0
    ) -> List[Dict]:
        """
        Advanced search for patients
        """
        # Resolve hospital_id from role_entity_id (assistant ID)
        hospital_id = await self._resolve_hospital_id(role_entity_id)
        
        base_query = {"role_entity_id": hospital_id}
        
        # Map of frontend field names to MongoDB field paths
        field_mappings = {
            "id": "id",
            "name": ["name.given", "name.family"],
            "gender": "gender",
            "birthDate": "birthDate",
            "phone": "telecom.value",
            "address": ["address.line", "address.city", "address.state", "address.postalCode", "address.country"]
        }
        
        # If field is specified, search in that field
        if field and field in field_mappings:
            field_path = field_mappings[field]
            
            # Handle the specific operator
            if operator:
                if isinstance(field_path, list):
                    # For fields that map to multiple paths
                    field_conditions = []
                    for path in field_path:
                        field_conditions.append(self._build_query_condition(path, operator, query))
                    base_query["$or"] = field_conditions
                else:
                    # For fields that map to a single path
                    base_query.update(self._build_query_condition(field_path, operator, query))
            else:
                # Default to contains if no operator is specified
                if isinstance(field_path, list):
                    field_conditions = []
                    for path in field_path:
                        field_conditions.append({path: {"$regex": query, "$options": "i"}})
                    base_query["$or"] = field_conditions
                else:
                    base_query[field_path] = {"$regex": query, "$options": "i"}
        else:
            # If no field is specified, search across all fields
            search_conditions = []
            for field_key, field_path in field_mappings.items():
                if isinstance(field_path, list):
                    for path in field_path:
                        search_conditions.append({path: {"$regex": query, "$options": "i"}})
                else:
                    search_conditions.append({field_path: {"$regex": query, "$options": "i"}})
            
            base_query["$or"] = search_conditions
        
        # Execute query
        cursor = self.patient_collection.find(base_query).skip(skip).limit(limit)
        patients = list(cursor)
        return [serialize_document(patient) for patient in patients]

    def _build_query_condition(self, field_path: str, operator: str, value: str) -> Dict:
        """
        Build MongoDB query condition based on the operator
        """
        if operator == "is":
            return {field_path: value}
        elif operator == "contains":
            return {field_path: {"$regex": value, "$options": "i"}}
        elif operator == "startsWith":
            return {field_path: {"$regex": f"^{value}", "$options": "i"}}
        elif operator == "endsWith":
            return {field_path: {"$regex": f"{value}$", "$options": "i"}}
        elif operator == "gt":
            return {field_path: {"$gt": value}}
        elif operator == "lt":
            return {field_path: {"$lt": value}}
        elif operator == "between":
            values = value.split(',')
            if len(values) == 2:
                return {field_path: {"$gte": values[0], "$lte": values[1]}}
            else:
                return {field_path: {"$regex": value, "$options": "i"}}
        else:
            return {field_path: {"$regex": value, "$options": "i"}}
