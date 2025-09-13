
import pandas as pd
import asyncio
from datetime import datetime
from .fetchController import serialize_document
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, UploadFile
import uuid
import io
from pymongo import MongoClient
from pymongo.collection import Collection

from api_gateway.database.db import get_database
from .schema import (
    FHIRResourceType, UploadStatus, ProcessingStatus,
    FHIRConversionStatus, MappingTemplate, ProcessingReport,
    ValidationError, CSVMappingRequest, MappingTemplateRequest,
    FHIRPatient, FHIRCondition, FHIRObservation, FHIREncounter, FHIRProcedure,
    FHIRName, FHIRAddress, FHIRTelecom, FHIRCodeableConcept, FHIRCoding,
    FHIRReference, FHIRQuantity, FHIRPeriod, FHIREncounterClass, FHIRIdentifier,
    FHIRMeta, FHIRProcedurePerformer, FHIREncounterLocation
)


class FHIRCSVProcessor:
    def __init__(self):
        self.db = get_database()
        self.conversion_status_collection = self.db.fhir_conversion_status
        self.mapping_templates_collection = self.db.mapping_templates
        self.fhir_resources_collection = self.db.fhir_resources
        # Add resource-specific collections
        self.resource_collections = {
            "Patient": self.db.fhir_patient,
            "Condition": self.db.fhir_condition,
            "Observation": self.db.fhir_observation,
            "Encounter": self.db.fhir_encounter,
            "Procedure": self.db.fhir_procedure
        }

    def _get_default_system_values(self, resource_type: str) -> Dict[str, Any]:
        """Get default system values for different resource types"""
        defaults = {
            "Patient": {
                "identifier_system": "http://hospital.local/patients",
                "identifier_use": "usual",
                "name_use": "official",
                "address_use": "home",
                "telecom_use": "home"
            },
            "Condition": {
                "identifier_system": "http://hospital.local/conditions",
                "clinical_status_system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                "verification_status_system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                "category_system": "http://terminology.hl7.org/CodeSystem/condition-category",
                "code_system": "http://snomed.info/sct"
            },
            "Observation": {
                "identifier_system": "http://hospital.local/observations",
                "status": "final",
                "category_system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code_system": "http://loinc.org"
            },
            "Encounter": {
                "identifier_system": "http://hospital.local/encounters",
                "status": "finished",
                "class_system": "http://terminology.hl7.org/CodeSystem/v3-ActCode"
            },
            "Procedure": {
                "identifier_system": "http://hospital.local/procedures",
                "status": "completed",
                "code_system": "http://snomed.info/sct"
            }
        }
        return defaults.get(resource_type, {})

    def _get_mapped_value(self, row: pd.Series, mapping_dict: Dict, field_name: str) -> Optional[str]:
        """Safely get mapped value from row, handling NaN and missing values"""
        
        # Handle both frontend format (Patient.id) and backend format (id)
        full_field_name = field_name
        if not field_name.startswith(('Patient.', 'Condition.', 'Observation.', 'Encounter.', 'Procedure.')):
            # Try to find the field with resource prefix
            resource_prefixes = ['Patient.', 'Condition.', 'Observation.', 'Encounter.', 'Procedure.']
            for prefix in resource_prefixes:
                prefixed_field = f"{prefix}{field_name}"
                if prefixed_field in mapping_dict:
                    full_field_name = prefixed_field
                    break
        
        if full_field_name not in mapping_dict:
            return None
            
        csv_column = mapping_dict[full_field_name]
        if csv_column not in row:
            return None
            
        value = row[csv_column]
        
        # Handle pandas NaN, None, and empty strings
        if pd.isna(value) or value is None or str(value).strip() == '':
            return None
            
        return str(value).strip()

    def _create_patient_key(self, row: pd.Series, mapping_dict: Dict) -> str:
        """Create a unique patient key based on available identifiers"""
        # Try to get patient ID first
        patient_id = self._get_mapped_value(row, mapping_dict, "id")
        if patient_id:
            return f"patient_{patient_id}"
        
        # Try name + birthdate combination
        family_name = self._get_mapped_value(row, mapping_dict, "name.family")
        given_name = self._get_mapped_value(row, mapping_dict, "name.given")
        birth_date = self._get_mapped_value(row, mapping_dict, "birthDate")
        
        if family_name and given_name and birth_date:
            return f"patient_{family_name}_{given_name}_{birth_date}".replace(" ", "_").lower()
        
        # Fallback to a generated key
        return f"patient_{str(uuid.uuid4())}"

    async def process_all_resources_with_relationships(
        self, 
        df: pd.DataFrame, 
        mappings_by_resource: Dict[str, Dict[str, str]], 
        upload_id: str, 
        role_entity_id: str,
        file_name: str
    ) -> Dict[str, Any]:
        """Process all resources with proper relationships"""
        
        results = {
            "processed_counts": {},
            "errors": [],
            "message": ""
        }
        
        # First pass: Create patients and establish patient keys
        patient_keys_map = {}  # Maps row index to patient key
        
        # Process patients first if mapping exists
        if "Patient" in mappings_by_resource and mappings_by_resource["Patient"]:
            patient_resources = []
            for index, row in df.iterrows():
                try:
                    patient_key = self._create_patient_key(row, mappings_by_resource["Patient"])
                    patient_keys_map[index] = patient_key
                    
                    # Check if patient already exists for this key
                    existing_patient = self.resource_collections["Patient"].find_one({
                        "patient_key": patient_key,
                        "role_entity_id": role_entity_id
                    })
                    
                    if not existing_patient:
                        patient_resource = await self._create_patient_resource(
                            row, mappings_by_resource["Patient"], str(uuid.uuid4()), 
                            upload_id, role_entity_id, patient_key
                        )
                        if patient_resource:
                            patient_resources.append(patient_resource)
                    
                except Exception as e:
                    results["errors"].append(f"Error processing patient row {index}: {str(e)}")
            
            if patient_resources:
                await self._save_fhir_resources(patient_resources, "Patient")
                results["processed_counts"]["Patient"] = len(patient_resources)

        # Second pass: Process other resources with patient references
        for resource_type in ["Condition", "Observation", "Encounter", "Procedure"]:
            if resource_type in mappings_by_resource and mappings_by_resource[resource_type]:
                resources = []
                for index, row in df.iterrows():
                    try:
                        # Get patient key for this row
                        patient_key = patient_keys_map.get(index)
                        if not patient_key and "Patient" in mappings_by_resource:
                            patient_key = self._create_patient_key(row, mappings_by_resource["Patient"])
                        
                        resource = await self._convert_row_to_fhir(
                            row, FHIRResourceType(resource_type), 
                            mappings_by_resource[resource_type], 
                            upload_id, role_entity_id, patient_key
                        )
                        
                        if resource:
                            resources.append(resource)
                            
                    except Exception as e:
                        results["errors"].append(f"Error processing {resource_type} row {index}: {str(e)}")
                
                if resources:
                    await self._save_fhir_resources(resources, resource_type)
                    results["processed_counts"][resource_type] = len(resources)

        # Create summary message
        messages = []
        for resource_type, count in results["processed_counts"].items():
            messages.append(f"{resource_type}: {count} resources")
        
        results["message"] = "; ".join(messages) if messages else "No resources processed"
        
        # Save conversion status
        await self._save_conversion_status_summary(
            upload_id, role_entity_id, file_name, results
        )
        
        return results

    async def _convert_row_to_fhir(
        self, 
        row: pd.Series, 
        resource_type: FHIRResourceType, 
        mappings_dict: Dict[str, str],
        upload_id: str,
        role_entity_id: str,
        patient_key: Optional[str] = None
    ):
        """Convert a single CSV row to FHIR resource"""
        
        resource_id = str(uuid.uuid4())
        
        if resource_type == FHIRResourceType.PATIENT:
            return await self._create_patient_resource(
                row, mappings_dict, resource_id, upload_id, role_entity_id, patient_key
            )
        elif resource_type == FHIRResourceType.CONDITION:
            return await self._create_condition_resource(
                row, mappings_dict, resource_id, upload_id, role_entity_id, patient_key
            )
        elif resource_type == FHIRResourceType.OBSERVATION:
            return await self._create_observation_resource(
                row, mappings_dict, resource_id, upload_id, role_entity_id, patient_key
            )
        elif resource_type == FHIRResourceType.ENCOUNTER:
            return await self._create_encounter_resource(
                row, mappings_dict, resource_id, upload_id, role_entity_id, patient_key
            )
        elif resource_type == FHIRResourceType.PROCEDURE:
            return await self._create_procedure_resource(
                row, mappings_dict, resource_id, upload_id, role_entity_id, patient_key
            )
        
        return None

    async def _create_patient_resource(self, row, mapping_dict, resource_id, upload_id, role_entity_id, patient_key=None):
        """Create FHIR Patient resource with complete field mapping"""
        
        defaults = self._get_default_system_values("Patient")
        
        patient = FHIRPatient(
            id=resource_id,
            upload_id=upload_id,
            role_entity_id=role_entity_id,
            created_at=datetime.utcnow(),
            resourceType="Patient",
            patient_key=patient_key or self._create_patient_key(row, mapping_dict)
        )
        
        # Auto-populate meta
        patient.meta = FHIRMeta(
            versionId="1",
            lastUpdated=datetime.utcnow().isoformat()
        )
        
        # Map basic fields
        gender = self._get_mapped_value(row, mapping_dict, "gender")
        if gender:
            patient.gender = gender.lower()
        
        birth_date = self._get_mapped_value(row, mapping_dict, "birthDate")
        if birth_date:
            patient.birthDate = birth_date
        
        # Map identifier with defaults
        identifier_value = self._get_mapped_value(row, mapping_dict, "identifier.value") or patient.id
        if identifier_value:
            identifier = FHIRIdentifier(
                use=defaults["identifier_use"],
                system=defaults["identifier_system"],
                value=identifier_value
            )
            patient.identifier = [identifier]
        
        # Map name with defaults
        family_name = self._get_mapped_value(row, mapping_dict, "name.family")
        given_name = self._get_mapped_value(row, mapping_dict, "name.given")
        
        if family_name or given_name:
            name = FHIRName(use=defaults["name_use"])
            if family_name:
                name.family = family_name
            if given_name:
                name.given = [given_name]
            patient.name = [name]
        
        # Map address with defaults
        address_fields = ["address.line", "address.city", "address.state", "address.postalCode", "address.country"]
        address_values = {field.split(".")[-1]: self._get_mapped_value(row, mapping_dict, field) for field in address_fields}
        
        if any(address_values.values()):
            address = FHIRAddress(use=defaults["address_use"])
            if address_values["line"]:
                address.line = [address_values["line"]]
            address.city = address_values["city"]
            address.state = address_values["state"]
            address.postalCode = address_values["postalCode"]
            address.country = address_values["country"]
            patient.address = [address]
        
        # Map telecom with defaults
        phone = self._get_mapped_value(row, mapping_dict, "telecom")
        email = self._get_mapped_value(row, mapping_dict, "telecom.email")
        
        telecoms = []
        if phone:
            telecoms.append(FHIRTelecom(
                system="phone",
                value=phone,
                use=defaults["telecom_use"]
            ))
        if email:
            telecoms.append(FHIRTelecom(
                system="email",
                value=email,
                use=defaults["telecom_use"]
            ))
        
        if telecoms:
            patient.telecom = telecoms
        
        return patient

    async def _create_condition_resource(self, row, mapping_dict, resource_id, upload_id, role_entity_id, patient_key):
        """Create FHIR Condition resource with complete field mapping"""
        
        defaults = self._get_default_system_values("Condition")
        
        condition = FHIRCondition(
            id=resource_id,
            upload_id=upload_id,
            role_entity_id=role_entity_id,
            created_at=datetime.utcnow(),
            resourceType="Condition",
            patient_key=patient_key
        )
        
        # Auto-populate meta
        condition.meta = FHIRMeta(
            versionId="1",
            lastUpdated=datetime.utcnow().isoformat()
        )
        
        # Map identifier
        identifier_value = self._get_mapped_value(row, mapping_dict, "identifier.value") or condition.id
        if identifier_value:
            identifier = FHIRIdentifier(
                use="usual",
                system=defaults["identifier_system"],
                value=identifier_value
            )
            condition.identifier = [identifier]
        
        # Map subject reference to patient
        if patient_key:
            condition.subject = FHIRReference(
                reference=f"Patient/{patient_key}",
                display="Patient"
            )
        
        # Map code with defaults
        code_value = self._get_mapped_value(row, mapping_dict, "code")
        code_display = self._get_mapped_value(row, mapping_dict, "code.display")
        if code_value:
            coding = FHIRCoding(
                system=defaults["code_system"],
                code=code_value,
                display=code_display
            )
            condition.code = FHIRCodeableConcept(
                coding=[coding],
                text=code_display or code_value
            )
        
        # Map clinical status with defaults
        clinical_status = self._get_mapped_value(row, mapping_dict, "clinicalStatus") or "active"
        coding = FHIRCoding(
            system=defaults["clinical_status_system"],
            code=clinical_status,
            display=clinical_status.capitalize()
        )
        condition.clinicalStatus = FHIRCodeableConcept(coding=[coding])
        
        # Map verification status with defaults
        verification_status = self._get_mapped_value(row, mapping_dict, "verificationStatus") or "confirmed"
        coding = FHIRCoding(
            system=defaults["verification_status_system"],
            code=verification_status,
            display=verification_status.capitalize()
        )
        condition.verificationStatus = FHIRCodeableConcept(coding=[coding])
        
        # Map category with defaults
        category_code = self._get_mapped_value(row, mapping_dict, "category") or "encounter-diagnosis"
        coding = FHIRCoding(
            system=defaults["category_system"],
            code=category_code,
            display="Encounter Diagnosis"
        )
        condition.category = [FHIRCodeableConcept(coding=[coding])]
        
        # Map dates
        onset_date = self._get_mapped_value(row, mapping_dict, "onsetDateTime")
        if onset_date:
            condition.onsetDateTime = onset_date
        
        recorded_date = self._get_mapped_value(row, mapping_dict, "recordedDate")
        if recorded_date:
            condition.recordedDate = recorded_date
        else:
            condition.recordedDate = datetime.utcnow().isoformat()
        
        return condition

    async def _create_observation_resource(self, row, mapping_dict, resource_id, upload_id, role_entity_id, patient_key):
        """Create FHIR Observation resource with complete field mapping"""
        
        defaults = self._get_default_system_values("Observation")
        
        observation = FHIRObservation(
            id=resource_id,
            upload_id=upload_id,
            role_entity_id=role_entity_id,
            created_at=datetime.utcnow(),
            resourceType="Observation",
            patient_key=patient_key
        )
        
        # Auto-populate meta
        observation.meta = FHIRMeta(
            versionId="1",
            lastUpdated=datetime.utcnow().isoformat()
        )
        
        # Map identifier
        identifier_value = self._get_mapped_value(row, mapping_dict, "identifier.value") or observation.id
        if identifier_value:
            identifier = FHIRIdentifier(
                use="usual",
                system=defaults["identifier_system"],
                value=identifier_value
            )
            observation.identifier = [identifier]
        
        # Map subject reference to patient
        if patient_key:
            observation.subject = FHIRReference(
                reference=f"Patient/{patient_key}",
                display="Patient"
            )
        
        # Map status with default
        observation.status = self._get_mapped_value(row, mapping_dict, "status") or defaults["status"]
        
        # Map category with defaults
        category_code = self._get_mapped_value(row, mapping_dict, "category") or "vital-signs"
        coding = FHIRCoding(
            system=defaults["category_system"],
            code=category_code,
            display="Vital Signs"
        )
        observation.category = [FHIRCodeableConcept(coding=[coding])]
        
        # Map code
        code_value = self._get_mapped_value(row, mapping_dict, "code")
        code_display = self._get_mapped_value(row, mapping_dict, "code.display")
        if code_value:
            coding = FHIRCoding(
                system=defaults["code_system"],
                code=code_value,
                display=code_display
            )
            observation.code = FHIRCodeableConcept(
                coding=[coding],
                text=code_display or code_value
            )
        
        # Map effective date
        effective_date = self._get_mapped_value(row, mapping_dict, "effectiveDateTime")
        if effective_date:
            observation.effectiveDateTime = effective_date
        else:
            observation.effectiveDateTime = datetime.utcnow().isoformat()
        
        # Map value quantity
        value_str = self._get_mapped_value(row, mapping_dict, "valueQuantity.value")
        unit = self._get_mapped_value(row, mapping_dict, "valueQuantity.unit")
        
        if value_str:
            try:
                value_float = float(value_str)
                observation.valueQuantity = FHIRQuantity(
                    value=value_float,
                    unit=unit or "unit",
                    system="http://unitsofmeasure.org",
                    code=unit or "1"
                )
            except (ValueError, TypeError):
                print(f"Warning: Could not convert value '{value_str}' to float")
        
        return observation

    async def _create_encounter_resource(self, row, mapping_dict, resource_id, upload_id, role_entity_id, patient_key):
        """Create FHIR Encounter resource with complete field mapping"""
        
        defaults = self._get_default_system_values("Encounter")
        
        encounter = FHIREncounter(
            id=resource_id,
            upload_id=upload_id,
            role_entity_id=role_entity_id,
            created_at=datetime.utcnow(),
            resourceType="Encounter",
            patient_key=patient_key
        )
        
        # Auto-populate meta
        encounter.meta = FHIRMeta(
            versionId="1",
            lastUpdated=datetime.utcnow().isoformat()
        )
        
        # Map identifier
        identifier_value = self._get_mapped_value(row, mapping_dict, "identifier.value") or encounter.id
        if identifier_value:
            identifier = FHIRIdentifier(
                use="usual",  
                system=defaults["identifier_system"],
                value=identifier_value
            )
            encounter.identifier = [identifier]
        
        # Map subject reference to patient
        if patient_key:
            encounter.subject = FHIRReference(
                reference=f"Patient/{patient_key}",
                display="Patient"
            )
        
        # Map status with default
        encounter.status = self._get_mapped_value(row, mapping_dict, "status") or defaults["status"]
        
        # Map class with defaults
        class_code = self._get_mapped_value(row, mapping_dict, "class.code") or "AMB"
        encounter.class_ = FHIREncounterClass(
            system=defaults["class_system"],
            code=class_code,
            display="Ambulatory" if class_code == "AMB" else class_code
        )
        
        # Map type
        type_code = self._get_mapped_value(row, mapping_dict, "type")
        if type_code:
            coding = FHIRCoding(
                system="http://snomed.info/sct",
                code=type_code,
                display=type_code
            )
            encounter.type = [FHIRCodeableConcept(coding=[coding])]
        
        # Map period
        period_start = self._get_mapped_value(row, mapping_dict, "period.start")
        period_end = self._get_mapped_value(row, mapping_dict, "period.end")
        
        if period_start or period_end:
            period = FHIRPeriod()
            period.start = period_start or datetime.utcnow().isoformat()
            period.end = period_end
            encounter.period = period
        
        return encounter

    async def _create_procedure_resource(self, row, mapping_dict, resource_id, upload_id, role_entity_id, patient_key):
        """Create FHIR Procedure resource with complete field mapping"""
        
        defaults = self._get_default_system_values("Procedure")
        
        procedure = FHIRProcedure(
            id=resource_id,
            upload_id=upload_id,
            role_entity_id=role_entity_id,
            created_at=datetime.utcnow(),
            resourceType="Procedure",
            patient_key=patient_key
        )
        
        # Auto-populate meta
        procedure.meta = FHIRMeta(
            versionId="1",
            lastUpdated=datetime.utcnow().isoformat()
        )
        
        # Map identifier
        identifier_value = self._get_mapped_value(row, mapping_dict, "identifier.value") or procedure.id
        if identifier_value:
            identifier = FHIRIdentifier(
                use="usual",
                system=defaults["identifier_system"],
                value=identifier_value
            )
            procedure.identifier = [identifier]
        
        # Map subject reference to patient
        if patient_key:
            procedure.subject = FHIRReference(
                reference=f"Patient/{patient_key}",
                display="Patient"
            )
        
        # Map status with default
        procedure.status = self._get_mapped_value(row, mapping_dict, "status") or defaults["status"]
        
        # Map code
        code_value = self._get_mapped_value(row, mapping_dict, "code")
        code_display = self._get_mapped_value(row, mapping_dict, "code.display")
        if code_value:
            coding = FHIRCoding(
                system=defaults["code_system"],
                code=code_value,
                display=code_display
            )
            procedure.code = FHIRCodeableConcept(
                coding=[coding],
                text=code_display or code_value
            )
        
        # Map performed date
        performed_date = self._get_mapped_value(row, mapping_dict, "performedDateTime")
        if performed_date:
            procedure.performedDateTime = performed_date
        else:
            procedure.performedDateTime = datetime.utcnow().isoformat()
        
        return procedure

    async def _save_fhir_resources(self, resources: List, resource_type: str = None):
        """Save FHIR resources to MongoDB, optionally to resource-specific collection"""
        if resources:
            resource_dicts = []
            for resource in resources:
                resource_dict = resource.dict()
                if not resource_dict.get('resourceType'):
                    resource_dict['resourceType'] = resource.__class__.__name__.replace('FHIR', '')
                resource_dicts.append(resource_dict)
            
            # Save to resource-specific collection if provided
            if resource_type and resource_type in self.resource_collections:
                collection = self.resource_collections[resource_type]
            else:
                collection = self.fhir_resources_collection
            
            print(f"Saving {len(resource_dicts)} resources to collection: {collection.name}")
            collection.insert_many(resource_dicts)

    async def _save_conversion_status_summary(self, upload_id: str, role_entity_id: str, file_name: str, results: Dict):
        """Save conversion status summary"""
        status = {
            "upload_id": upload_id,
            "role_entity_id": role_entity_id,
            "file_name": file_name,
            "status": "completed",
            "started_at": datetime.utcnow(),
            "completed_at": datetime.utcnow(),
            "resource_counts": results["processed_counts"],
            "errors": results["errors"]
        }
        
        self.conversion_status_collection.replace_one(
            {"upload_id": upload_id},
            status,
            upsert=True
        )

    async def get_patient_complete_data(self, patient_key: str, role_entity_id: str):
        """Get complete patient data including all related resources"""
        result = {
            "patient": None,
            "conditions": [],
            "observations": [],
            "encounters": [],
            "procedures": []
        }
        
        # Get patient
        patient = self.resource_collections["Patient"].find_one({
            "patient_key": patient_key,
            "role_entity_id": role_entity_id
        })
        if patient:
            result["patient"] = patient
        
        # Get related resources
        for resource_type in ["Condition", "Observation", "Encounter", "Procedure"]:
            resources = list(self.resource_collections[resource_type].find({
                "patient_key": patient_key,
                "role_entity_id": role_entity_id
            }))
            result[resource_type.lower() + "s"] = resources
        
        return result

    async def get_conversions_by_role_entity(self, role_entity_id: str):
        """Get all conversions for a role entity"""
        cursor = self.conversion_status_collection.find({"role_entity_id": role_entity_id})
        return [serialize_document(doc) for doc in cursor]

    async def get_fhir_resources(
        self, 
        role_entity_id: str, 
        resource_type: Optional[str] = None,
        patient_key: Optional[str] = None,
        limit: int = 100,
        skip: int = 0
    ):
        """Get FHIR resources with optional filtering"""
        query = {"role_entity_id": role_entity_id}
        
        if patient_key:
            query["patient_key"] = patient_key
        
        if resource_type and resource_type in self.resource_collections:
            collection = self.resource_collections[resource_type]
        else:
            collection = self.fhir_resources_collection
            if resource_type:
                query["resourceType"] = resource_type
        
        cursor = collection.find(query).skip(skip).limit(limit)
        return [serialize_document(doc) for doc in cursor]

    async def save_mapping_template(self, request: MappingTemplateRequest) -> str:
        """Save mapping template to MongoDB"""
        template_id = str(uuid.uuid4())
        template = MappingTemplate(
            id=template_id,
            template_name=request.template_name,
            resource_type=request.resource_type,
            mappings=request.mappings,
            role_entity_id=request.role_entity_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.mapping_templates_collection.insert_one(template.dict())
        return template_id

    async def get_mapping_templates(self, role_entity_id: str) -> List[MappingTemplate]:
        """Get all mapping templates for a role entity"""
        docs = self.mapping_templates_collection.find({"role_entity_id": role_entity_id})
        return [MappingTemplate(**doc) for doc in docs]
