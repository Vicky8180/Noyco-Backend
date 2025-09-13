# # # from pydantic import BaseModel, Field
# # # from typing import List, Dict, Any, Optional
# # # from enum import Enum
# # # from datetime import datetime


# # # class FHIRResourceType(str, Enum):
# # #     PATIENT = "Patient"
# # #     CONDITION = "Condition"
# # #     OBSERVATION = "Observation"
# # #     ENCOUNTER = "Encounter"
# # #     PROCEDURE = "Procedure"


# # # class UploadStatus(str, Enum):
# # #     PENDING = "pending"
# # #     PROCESSING = "processing"
# # #     COMPLETED = "completed"
# # #     FAILED = "failed"


# # # class FileUploadRequest(BaseModel):
# # #     role_entity_id: str
# # #     file_name: str
# # #     file_type: str
# # #     content_type: str


# # # class FileUploadResponse(BaseModel):
# # #     upload_id: str
# # #     status: UploadStatus
# # #     presigned_url: Optional[str] = None
# # #     message: str


# # # class ProcessFileRequest(BaseModel):
# # #     upload_id: str
# # #     role_entity_id: str


# # # class ProcessFileResponse(BaseModel):
# # #     upload_id: str
# # #     status: UploadStatus
# # #     resource_counts: Dict[str, int] = Field(default_factory=dict)
# # #     errors: List[str] = Field(default_factory=list)
# # #     message: str


# # # class FHIRConversionStatus(BaseModel):
# # #     upload_id: str
# # #     role_entity_id: str
# # #     file_name: str
# # #     status: UploadStatus
# # #     started_at: datetime
# # #     completed_at: Optional[datetime] = None
# # #     resource_counts: Dict[str, int] = Field(default_factory=dict)
# # #     errors: List[str] = Field(default_factory=list)


# # # class FHIRConversionListResponse(BaseModel):
# # #     conversions: List[FHIRConversionStatus]
# # #     total: int


# # # # FHIR Meta Information
# # # class FHIRMeta(BaseModel):
# # #     versionId: Optional[str] = None
# # #     lastUpdated: Optional[str] = None


# # # # FHIR Identifier
# # # class FHIRIdentifier(BaseModel):
# # #     use: Optional[str] = None
# # #     system: Optional[str] = None
# # #     value: Optional[str] = None


# # # # FHIR Name
# # # class FHIRName(BaseModel):
# # #     use: Optional[str] = None
# # #     family: Optional[str] = None
# # #     given: List[str] = Field(default_factory=list)


# # # # FHIR Address
# # # class FHIRAddress(BaseModel):
# # #     use: Optional[str] = None
# # #     line: List[str] = Field(default_factory=list)
# # #     city: Optional[str] = None
# # #     state: Optional[str] = None
# # #     postalCode: Optional[str] = None
# # #     country: Optional[str] = None


# # # # FHIR Telecom
# # # class FHIRTelecom(BaseModel):
# # #     system: Optional[str] = None
# # #     value: Optional[str] = None
# # #     use: Optional[str] = None


# # # # FHIR Reference
# # # class FHIRReference(BaseModel):
# # #     reference: Optional[str] = None
# # #     display: Optional[str] = None


# # # # FHIR Coding
# # # class FHIRCoding(BaseModel):
# # #     system: Optional[str] = None
# # #     code: Optional[str] = None
# # #     display: Optional[str] = None


# # # # FHIR CodeableConcept
# # # class FHIRCodeableConcept(BaseModel):
# # #     coding: List[FHIRCoding] = Field(default_factory=list)
# # #     text: Optional[str] = None


# # # # FHIR Quantity
# # # class FHIRQuantity(BaseModel):
# # #     value: Optional[float] = None
# # #     unit: Optional[str] = None
# # #     system: Optional[str] = None
# # #     code: Optional[str] = None


# # # # FHIR Period
# # # class FHIRPeriod(BaseModel):
# # #     start: Optional[str] = None
# # #     end: Optional[str] = None


# # # # FHIR Patient Resource
# # # class FHIRPatient(BaseModel):
# # #     resourceType: str = "Patient"
# # #     id: str
# # #     meta: Optional[FHIRMeta] = None
# # #     active: Optional[bool] = True
# # #     identifier: List[FHIRIdentifier] = Field(default_factory=list)
# # #     name: List[FHIRName] = Field(default_factory=list)
# # #     gender: Optional[str] = None
# # #     birthDate: Optional[str] = None
# # #     address: List[FHIRAddress] = Field(default_factory=list)
# # #     telecom: List[FHIRTelecom] = Field(default_factory=list)
# # #     managingOrganization: Optional[FHIRReference] = None


# # # # FHIR Condition Resource
# # # class FHIRCondition(BaseModel):
# # #     resourceType: str = "Condition"
# # #     id: str
# # #     meta: Optional[FHIRMeta] = None
# # #     identifier: List[FHIRIdentifier] = Field(default_factory=list)
# # #     subject: Optional[FHIRReference] = None
# # #     clinicalStatus: Optional[FHIRCodeableConcept] = None
# # #     verificationStatus: Optional[FHIRCodeableConcept] = None
# # #     category: List[FHIRCodeableConcept] = Field(default_factory=list)
# # #     code: Optional[FHIRCodeableConcept] = None
# # #     onsetDateTime: Optional[str] = None
# # #     recordedDate: Optional[str] = None


# # # # FHIR Observation Resource
# # # class FHIRObservation(BaseModel):
# # #     resourceType: str = "Observation"
# # #     id: str
# # #     meta: Optional[FHIRMeta] = None
# # #     identifier: List[FHIRIdentifier] = Field(default_factory=list)
# # #     status: Optional[str] = None
# # #     category: List[FHIRCodeableConcept] = Field(default_factory=list)
# # #     code: Optional[FHIRCodeableConcept] = None
# # #     subject: Optional[FHIRReference] = None
# # #     effectiveDateTime: Optional[str] = None
# # #     valueQuantity: Optional[FHIRQuantity] = None


# # # # FHIR Encounter Class
# # # class FHIREncounterClass(BaseModel):
# # #     system: Optional[str] = None
# # #     code: Optional[str] = None
# # #     display: Optional[str] = None


# # # # FHIR Encounter Location
# # # class FHIREncounterLocation(BaseModel):
# # #     location: Optional[FHIRReference] = None


# # # # FHIR Encounter Resource
# # # class FHIREncounter(BaseModel):
# # #     resourceType: str = "Encounter"
# # #     id: str
# # #     meta: Optional[FHIRMeta] = None
# # #     identifier: List[FHIRIdentifier] = Field(default_factory=list)
# # #     status: Optional[str] = None
# # #     class_: Optional[FHIREncounterClass] = Field(None, alias="class")
# # #     type: List[FHIRCodeableConcept] = Field(default_factory=list)
# # #     subject: Optional[FHIRReference] = None
# # #     period: Optional[FHIRPeriod] = None
# # #     reasonCode: List[FHIRCodeableConcept] = Field(default_factory=list)
# # #     location: List[FHIREncounterLocation] = Field(default_factory=list)


# # # # FHIR Procedure Performer
# # # class FHIRProcedurePerformer(BaseModel):
# # #     actor: Optional[FHIRReference] = None


# # # # FHIR Procedure Resource
# # # class FHIRProcedure(BaseModel):
# # #     resourceType: str = "Procedure"
# # #     id: str
# # #     meta: Optional[FHIRMeta] = None
# # #     identifier: List[FHIRIdentifier] = Field(default_factory=list)
# # #     status: Optional[str] = None
# # #     subject: Optional[FHIRReference] = None
# # #     code: Optional[FHIRCodeableConcept] = None
# # #     performedDateTime: Optional[str] = None
# # #     reasonCode: List[FHIRCodeableConcept] = Field(default_factory=list)
# # #     performer: List[FHIRProcedurePerformer] = Field(default_factory=list)




# # # schema.py
# # from pydantic import BaseModel, Field
# # from typing import List, Dict, Any, Optional
# # from enum import Enum
# # from datetime import datetime


# # class FHIRResourceType(str, Enum):
# #     PATIENT = "Patient"
# #     CONDITION = "Condition"
# #     OBSERVATION = "Observation"
# #     ENCOUNTER = "Encounter"
# #     PROCEDURE = "Procedure"


# # class UploadStatus(str, Enum):
# #     PENDING = "pending"
# #     PROCESSING = "processing"
# #     COMPLETED = "completed"
# #     FAILED = "failed"


# # class ProcessingStatus(str, Enum):
# #     QUEUED = "queued"
# #     IN_PROGRESS = "in_progress"
# #     COMPLETED = "completed"
# #     FAILED = "failed"


# # # Request Models
# # class FieldMapping(BaseModel):
# #     fhir_field: str
# #     csv_column: str


# # class CSVMappingRequest(BaseModel):
# #     resource_type: FHIRResourceType
# #     mappings: List[FieldMapping]
# #     file_name: str
# #     role_entity_id: str


# # class MappingTemplateRequest(BaseModel):
# #     template_name: str
# #     resource_type: FHIRResourceType
# #     mappings: Dict[str, str]  # fhir_field -> csv_column
# #     role_entity_id: str


# # # Response Models
# # class ProcessingResponse(BaseModel):
# #     upload_id: str
# #     status: ProcessingStatus
# #     message: str


# # class FHIRConversionStatus(BaseModel):
# #     upload_id: str
# #     role_entity_id: str
# #     file_name: str
# #     resource_type: FHIRResourceType
# #     status: UploadStatus
# #     started_at: datetime
# #     completed_at: Optional[datetime] = None
# #     total_rows: int = 0
# #     processed_rows: int = 0
# #     failed_rows: int = 0
# #     resource_counts: Dict[str, int] = Field(default_factory=dict)
# #     errors: List[str] = Field(default_factory=list)
# #     mappings: Dict[str, str] = Field(default_factory=dict)


# # class MappingTemplate(BaseModel):
# #     id: str
# #     template_name: str
# #     resource_type: FHIRResourceType
# #     mappings: Dict[str, str]
# #     role_entity_id: str
# #     created_at: datetime
# #     updated_at: datetime


# # class ValidationError(BaseModel):
# #     field: str
# #     error: str
# #     row_number: int


# # class ProcessingReport(BaseModel):
# #     upload_id: str
# #     total_processed: int
# #     successful: int
# #     failed: int
# #     validation_errors: List[ValidationError]
# #     created_resources: List[str]


# # # FHIR Resource Models (Enhanced from your existing models)
# # class FHIRMeta(BaseModel):
# #     versionId: Optional[str] = None
# #     lastUpdated: Optional[str] = None


# # class FHIRIdentifier(BaseModel):
# #     use: Optional[str] = None
# #     system: Optional[str] = None
# #     value: Optional[str] = None


# # class FHIRName(BaseModel):
# #     use: Optional[str] = None
# #     family: Optional[str] = None
# #     given: List[str] = Field(default_factory=list)


# # class FHIRAddress(BaseModel):
# #     use: Optional[str] = None
# #     line: List[str] = Field(default_factory=list)
# #     city: Optional[str] = None
# #     state: Optional[str] = None
# #     postalCode: Optional[str] = None
# #     country: Optional[str] = None


# # class FHIRTelecom(BaseModel):
# #     system: Optional[str] = None
# #     value: Optional[str] = None
# #     use: Optional[str] = None


# # class FHIRReference(BaseModel):
# #     reference: Optional[str] = None
# #     display: Optional[str] = None


# # class FHIRCoding(BaseModel):
# #     system: Optional[str] = None
# #     code: Optional[str] = None
# #     display: Optional[str] = None


# # class FHIRCodeableConcept(BaseModel):
# #     coding: List[FHIRCoding] = Field(default_factory=list)
# #     text: Optional[str] = None


# # class FHIRQuantity(BaseModel):
# #     value: Optional[float] = None
# #     unit: Optional[str] = None
# #     system: Optional[str] = None
# #     code: Optional[str] = None


# # class FHIRPeriod(BaseModel):
# #     start: Optional[str] = None
# #     end: Optional[str] = None


# # # Enhanced FHIR Resource Models
# # class FHIRPatient(BaseModel):
# #     resourceType: str = "Patient"
# #     id: str
# #     meta: Optional[FHIRMeta] = None
# #     active: Optional[bool] = True
# #     identifier: List[FHIRIdentifier] = Field(default_factory=list)
# #     name: List[FHIRName] = Field(default_factory=list)
# #     gender: Optional[str] = None
# #     birthDate: Optional[str] = None
# #     address: List[FHIRAddress] = Field(default_factory=list)
# #     telecom: List[FHIRTelecom] = Field(default_factory=list)
# #     managingOrganization: Optional[FHIRReference] = None
# #     # Additional metadata
# #     upload_id: Optional[str] = None
# #     role_entity_id: Optional[str] = None
# #     created_at: Optional[datetime] = None


# # class FHIRCondition(BaseModel):
# #     resourceType: str = "Condition"
# #     id: str
# #     meta: Optional[FHIRMeta] = None
# #     identifier: List[FHIRIdentifier] = Field(default_factory=list)
# #     subject: Optional[FHIRReference] = None
# #     clinicalStatus: Optional[FHIRCodeableConcept] = None
# #     verificationStatus: Optional[FHIRCodeableConcept] = None
# #     category: List[FHIRCodeableConcept] = Field(default_factory=list)
# #     code: Optional[FHIRCodeableConcept] = None
# #     onsetDateTime: Optional[str] = None
# #     recordedDate: Optional[str] = None
# #     # Additional metadata
# #     upload_id: Optional[str] = None
# #     role_entity_id: Optional[str] = None
# #     created_at: Optional[datetime] = None


# # class FHIRObservation(BaseModel):
# #     resourceType: str = "Observation"
# #     id: str
# #     meta: Optional[FHIRMeta] = None
# #     identifier: List[FHIRIdentifier] = Field(default_factory=list)
# #     status: Optional[str] = None
# #     category: List[FHIRCodeableConcept] = Field(default_factory=list)
# #     code: Optional[FHIRCodeableConcept] = None
# #     subject: Optional[FHIRReference] = None
# #     effectiveDateTime: Optional[str] = None
# #     valueQuantity: Optional[FHIRQuantity] = None
# #     # Additional metadata
# #     upload_id: Optional[str] = None
# #     role_entity_id: Optional[str] = None
# #     created_at: Optional[datetime] = None


# # class FHIREncounterClass(BaseModel):
# #     system: Optional[str] = None
# #     code: Optional[str] = None
# #     display: Optional[str] = None


# # class FHIREncounterLocation(BaseModel):
# #     location: Optional[FHIRReference] = None


# # class FHIREncounter(BaseModel):
# #     resourceType: str = "Encounter"
# #     id: str
# #     meta: Optional[FHIRMeta] = None
# #     identifier: List[FHIRIdentifier] = Field(default_factory=list)
# #     status: Optional[str] = None
# #     class_: Optional[FHIREncounterClass] = Field(None, alias="class")
# #     type: List[FHIRCodeableConcept] = Field(default_factory=list)
# #     subject: Optional[FHIRReference] = None
# #     period: Optional[FHIRPeriod] = None
# #     reasonCode: List[FHIRCodeableConcept] = Field(default_factory=list)
# #     location: List[FHIREncounterLocation] = Field(default_factory=list)
# #     # Additional metadata
# #     upload_id: Optional[str] = None
# #     role_entity_id: Optional[str] = None
# #     created_at: Optional[datetime] = None


# # class FHIRProcedurePerformer(BaseModel):
# #     actor: Optional[FHIRReference] = None


# # class FHIRProcedure(BaseModel):
# #     resourceType: str = "Procedure"
# #     id: str
# #     meta: Optional[FHIRMeta] = None
# #     identifier: List[FHIRIdentifier] = Field(default_factory=list)
# #     status: Optional[str] = None
# #     subject: Optional[FHIRReference] = None
# #     code: Optional[FHIRCodeableConcept] = None
# #     performedDateTime: Optional[str] = None
# #     reasonCode: List[FHIRCodeableConcept] = Field(default_factory=list)
# #     performer: List[FHIRProcedurePerformer] = Field(default_factory=list)
# #     # Additional metadata
# #     upload_id: Optional[str] = None
# #     role_entity_id: Optional[str] = None
# #     created_at: Optional[datetime] = None











# # class FileUploadRequest(BaseModel):
# #     role_entity_id: str
# #     file_name: str
# #     file_type: str
# #     content_type: str



# # class FileUploadResponse(BaseModel):
# #     upload_id: str
# #     status: UploadStatus
# #     presigned_url: Optional[str] = None
# #     message: str


# # class ProcessFileRequest(BaseModel):
# #     upload_id: str
# #     role_entity_id: str


# # class ProcessFileResponse(BaseModel):
# #     upload_id: str
# #     status: UploadStatus
# #     resource_counts: Dict[str, int] = Field(default_factory=dict)
# #     errors: List[str] = Field(default_factory=list)
# #     message: str

# # class FHIRConversionListResponse(BaseModel):
# #     conversions: List[FHIRConversionStatus]
# #     total: int



# # schema.py
# from pydantic import BaseModel, Field, validator
# from typing import List, Dict, Any, Optional, Union
# from enum import Enum
# from datetime import datetime


# class FHIRResourceType(str, Enum):
#     PATIENT = "Patient"
#     CONDITION = "Condition"
#     OBSERVATION = "Observation"
#     ENCOUNTER = "Encounter"
#     PROCEDURE = "Procedure"


# class UploadStatus(str, Enum):
#     PENDING = "pending"
#     PROCESSING = "processing"
#     COMPLETED = "completed"
#     FAILED = "failed"


# class ProcessingStatus(str, Enum):
#     QUEUED = "queued"
#     IN_PROGRESS = "in_progress"
#     COMPLETED = "completed"
#     FAILED = "failed"


# # Request Models
# class FieldMapping(BaseModel):
#     fhir_field: str
#     csv_column: str


# class CSVMappingRequest(BaseModel):
#     resource_type: FHIRResourceType
#     mappings: Union[List[FieldMapping], Dict[str, str]]  # Support both formats
#     file_name: str
#     role_entity_id: str
    
#     @validator('mappings', pre=True)
#     def validate_mappings(cls, v):
#         # If it's a string (JSON), parse it
#         if isinstance(v, str):
#             import json
#             v = json.loads(v)
#         return v


# class MappingTemplateRequest(BaseModel):
#     template_name: str
#     resource_type: FHIRResourceType
#     mappings: Dict[str, str]  # fhir_field -> csv_column
#     role_entity_id: str


# # Response Models
# class ProcessingResponse(BaseModel):
#     upload_id: str
#     status: ProcessingStatus
#     message: str


# class FHIRConversionStatus(BaseModel):
#     upload_id: str
#     role_entity_id: str
#     file_name: str
#     resource_type: FHIRResourceType
#     status: UploadStatus
#     started_at: datetime
#     completed_at: Optional[datetime] = None
#     total_rows: int = 0
#     processed_rows: int = 0
#     failed_rows: int = 0
#     resource_counts: Dict[str, int] = Field(default_factory=dict)
#     errors: List[str] = Field(default_factory=list)
#     mappings: Dict[str, str] = Field(default_factory=dict)


# class MappingTemplate(BaseModel):
#     id: str
#     template_name: str
#     resource_type: FHIRResourceType
#     mappings: Dict[str, str]
#     role_entity_id: str
#     created_at: datetime
#     updated_at: datetime


# class ValidationError(BaseModel):
#     field: str
#     error: str
#     row_number: int


# class ProcessingReport(BaseModel):
#     upload_id: str
#     total_processed: int
#     successful: int
#     failed: int
#     validation_errors: List[ValidationError]
#     created_resources: List[str]


# # FHIR Resource Models (Enhanced from your existing models)
# class FHIRMeta(BaseModel):
#     versionId: Optional[str] = None
#     lastUpdated: Optional[str] = None


# class FHIRIdentifier(BaseModel):
#     use: Optional[str] = None
#     system: Optional[str] = None
#     value: Optional[str] = None


# class FHIRName(BaseModel):
#     use: Optional[str] = None
#     family: Optional[str] = None
#     given: List[str] = Field(default_factory=list)


# class FHIRAddress(BaseModel):
#     use: Optional[str] = None
#     line: List[str] = Field(default_factory=list)
#     city: Optional[str] = None
#     state: Optional[str] = None
#     postalCode: Optional[str] = None
#     country: Optional[str] = None


# class FHIRTelecom(BaseModel):
#     system: Optional[str] = None
#     value: Optional[str] = None
#     use: Optional[str] = None


# class FHIRReference(BaseModel):
#     reference: Optional[str] = None
#     display: Optional[str] = None


# class FHIRCoding(BaseModel):
#     system: Optional[str] = None
#     code: Optional[str] = None
#     display: Optional[str] = None


# class FHIRCodeableConcept(BaseModel):
#     coding: List[FHIRCoding] = Field(default_factory=list)
#     text: Optional[str] = None


# class FHIRQuantity(BaseModel):
#     value: Optional[float] = None
#     unit: Optional[str] = None
#     system: Optional[str] = None
#     code: Optional[str] = None


# class FHIRPeriod(BaseModel):
#     start: Optional[str] = None
#     end: Optional[str] = None


# # Enhanced FHIR Resource Models
# class FHIRPatient(BaseModel):
#     resourceType: str = "Patient"
#     id: str
#     meta: Optional[FHIRMeta] = None
#     active: Optional[bool] = True
#     identifier: List[FHIRIdentifier] = Field(default_factory=list)
#     name: List[FHIRName] = Field(default_factory=list)
#     gender: Optional[str] = None
#     birthDate: Optional[str] = None
#     address: List[FHIRAddress] = Field(default_factory=list)
#     telecom: List[FHIRTelecom] = Field(default_factory=list)
#     managingOrganization: Optional[FHIRReference] = None
#     # Additional metadata
#     upload_id: Optional[str] = None
#     role_entity_id: Optional[str] = None
#     created_at: Optional[datetime] = None


# class FHIRCondition(BaseModel):
#     resourceType: str = "Condition"
#     id: str
#     meta: Optional[FHIRMeta] = None
#     identifier: List[FHIRIdentifier] = Field(default_factory=list)
#     subject: Optional[FHIRReference] = None
#     clinicalStatus: Optional[FHIRCodeableConcept] = None
#     verificationStatus: Optional[FHIRCodeableConcept] = None
#     category: List[FHIRCodeableConcept] = Field(default_factory=list)
#     code: Optional[FHIRCodeableConcept] = None
#     onsetDateTime: Optional[str] = None
#     recordedDate: Optional[str] = None
#     # Additional metadata
#     upload_id: Optional[str] = None
#     role_entity_id: Optional[str] = None
#     created_at: Optional[datetime] = None


# class FHIRObservation(BaseModel):
#     resourceType: str = "Observation"
#     id: str
#     meta: Optional[FHIRMeta] = None
#     identifier: List[FHIRIdentifier] = Field(default_factory=list)
#     status: Optional[str] = None
#     category: List[FHIRCodeableConcept] = Field(default_factory=list)
#     code: Optional[FHIRCodeableConcept] = None
#     subject: Optional[FHIRReference] = None
#     effectiveDateTime: Optional[str] = None
#     valueQuantity: Optional[FHIRQuantity] = None
#     # Additional metadata
#     upload_id: Optional[str] = None
#     role_entity_id: Optional[str] = None
#     created_at: Optional[datetime] = None


# class FHIREncounterClass(BaseModel):
#     system: Optional[str] = None
#     code: Optional[str] = None
#     display: Optional[str] = None


# class FHIREncounterLocation(BaseModel):
#     location: Optional[FHIRReference] = None


# class FHIREncounter(BaseModel):
#     resourceType: str = "Encounter"
#     id: str
#     meta: Optional[FHIRMeta] = None
#     identifier: List[FHIRIdentifier] = Field(default_factory=list)
#     status: Optional[str] = None
#     class_: Optional[FHIREncounterClass] = Field(None, alias="class")
#     type: List[FHIRCodeableConcept] = Field(default_factory=list)
#     subject: Optional[FHIRReference] = None
#     period: Optional[FHIRPeriod] = None
#     reasonCode: List[FHIRCodeableConcept] = Field(default_factory=list)
#     location: List[FHIREncounterLocation] = Field(default_factory=list)
#     # Additional metadata
#     upload_id: Optional[str] = None
#     role_entity_id: Optional[str] = None
#     created_at: Optional[datetime] = None


# class FHIRProcedurePerformer(BaseModel):
#     actor: Optional[FHIRReference] = None


# class FHIRProcedure(BaseModel):
#     resourceType: str = "Procedure"
#     id: str
#     meta: Optional[FHIRMeta] = None
#     identifier: List[FHIRIdentifier] = Field(default_factory=list)
#     status: Optional[str] = None
#     subject: Optional[FHIRReference] = None
#     code: Optional[FHIRCodeableConcept] = None
#     performedDateTime: Optional[str] = None
#     reasonCode: List[FHIRCodeableConcept] = Field(default_factory=list)
#     performer: List[FHIRProcedurePerformer] = Field(default_factory=list)
#     # Additional metadata
#     upload_id: Optional[str] = None
#     role_entity_id: Optional[str] = None
#     created_at: Optional[datetime] = None


# class FileUploadRequest(BaseModel):
#     role_entity_id: str
#     file_name: str
#     file_type: str
#     content_type: str


# class FileUploadResponse(BaseModel):
#     upload_id: str
#     status: UploadStatus
#     presigned_url: Optional[str] = None
#     message: str


# class ProcessFileRequest(BaseModel):
#     upload_id: str
#     role_entity_id: str


# class ProcessFileResponse(BaseModel):
#     upload_id: str
#     status: UploadStatus
#     resource_counts: Dict[str, int] = Field(default_factory=dict)
#     errors: List[str] = Field(default_factory=list)
#     message: str


# class FHIRConversionListResponse(BaseModel):
#     conversions: List[FHIRConversionStatus]
#     total: int




# schema.py
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional, Union
from enum import Enum
from datetime import datetime


class FHIRResourceType(str, Enum):
    PATIENT = "Patient"
    CONDITION = "Condition"
    OBSERVATION = "Observation"
    ENCOUNTER = "Encounter"
    PROCEDURE = "Procedure"


class UploadStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# Request Models
class FieldMapping(BaseModel):
    fhir_field: str
    csv_column: str


class CSVMappingRequest(BaseModel):
    resource_type: FHIRResourceType
    mappings: Union[List[FieldMapping], Dict[str, str]]  # Support both formats
    file_name: str
    role_entity_id: str
    
    @validator('mappings', pre=True)
    def validate_mappings(cls, v):
        # If it's a string (JSON), parse it
        if isinstance(v, str):
            import json
            v = json.loads(v)
        return v


class MappingTemplateRequest(BaseModel):
    template_name: str
    resource_type: FHIRResourceType
    mappings: Dict[str, str]  # fhir_field -> csv_column
    role_entity_id: str


# Response Models  
class ProcessingResponse(BaseModel):
    upload_id: str
    status: ProcessingStatus
    message: str


class FHIRConversionStatus(BaseModel):
    upload_id: str
    role_entity_id: str
    file_name: str
    resource_type: FHIRResourceType
    status: UploadStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_rows: int = 0
    processed_rows: int = 0
    failed_rows: int = 0
    resource_counts: Dict[str, int] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    mappings: Dict[str, str] = Field(default_factory=dict)


class MappingTemplate(BaseModel):
    id: str
    template_name: str
    resource_type: FHIRResourceType
    mappings: Dict[str, str]
    role_entity_id: str
    created_at: datetime
    updated_at: datetime


class ValidationError(BaseModel):
    field: str
    error: str
    row_number: int


class ProcessingReport(BaseModel):
    upload_id: str
    total_processed: int
    successful: int
    failed: int
    validation_errors: List[ValidationError]
    created_resources: List[str]


# FHIR Resource Models (Enhanced from your existing models)
class FHIRMeta(BaseModel):
    versionId: Optional[str] = None
    lastUpdated: Optional[str] = None


class FHIRIdentifier(BaseModel):
    use: Optional[str] = None
    system: Optional[str] = None
    value: Optional[str] = None


class FHIRName(BaseModel):
    use: Optional[str] = None
    family: Optional[str] = None
    given: List[str] = Field(default_factory=list)


class FHIRAddress(BaseModel):
    use: Optional[str] = None
    line: List[str] = Field(default_factory=list)
    city: Optional[str] = None
    state: Optional[str] = None
    postalCode: Optional[str] = None
    country: Optional[str] = None


class FHIRTelecom(BaseModel):
    system: Optional[str] = None
    value: Optional[str] = None
    use: Optional[str] = None


class FHIRReference(BaseModel):
    reference: Optional[str] = None
    display: Optional[str] = None


class FHIRCoding(BaseModel):
    system: Optional[str] = None
    code: Optional[str] = None
    display: Optional[str] = None


class FHIRCodeableConcept(BaseModel):
    coding: List[FHIRCoding] = Field(default_factory=list)
    text: Optional[str] = None


class FHIRQuantity(BaseModel):
    value: Optional[float] = None
    unit: Optional[str] = None
    system: Optional[str] = None
    code: Optional[str] = None


class FHIRPeriod(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None


# Enhanced FHIR Resource Models
class FHIRPatient(BaseModel):
    resourceType: str = "Patient"
    id: str
    meta: Optional[FHIRMeta] = None
    active: Optional[bool] = True
    identifier: List[FHIRIdentifier] = Field(default_factory=list)
    name: List[FHIRName] = Field(default_factory=list)
    gender: Optional[str] = None
    birthDate: Optional[str] = None
    address: List[FHIRAddress] = Field(default_factory=list)
    telecom: List[FHIRTelecom] = Field(default_factory=list)
    managingOrganization: Optional[FHIRReference] = None
    # Additional metadata
    upload_id: Optional[str] = None
    role_entity_id: Optional[str] = None
    created_at: Optional[datetime] = None
    patient_key: Optional[str] = None  # Key to link related resources


class FHIRCondition(BaseModel):
    resourceType: str = "Condition"
    id: str
    meta: Optional[FHIRMeta] = None
    identifier: List[FHIRIdentifier] = Field(default_factory=list)
    subject: Optional[FHIRReference] = None
    clinicalStatus: Optional[FHIRCodeableConcept] = None
    verificationStatus: Optional[FHIRCodeableConcept] = None
    category: List[FHIRCodeableConcept] = Field(default_factory=list)
    code: Optional[FHIRCodeableConcept] = None
    onsetDateTime: Optional[str] = None
    recordedDate: Optional[str] = None
    # Additional metadata
    upload_id: Optional[str] = None
    role_entity_id: Optional[str] = None
    created_at: Optional[datetime] = None
    patient_key: Optional[str] = None  # Key to link to patient


class FHIRObservation(BaseModel):
    resourceType: str = "Observation"
    id: str
    meta: Optional[FHIRMeta] = None
    identifier: List[FHIRIdentifier] = Field(default_factory=list)
    status: Optional[str] = None
    category: List[FHIRCodeableConcept] = Field(default_factory=list)
    code: Optional[FHIRCodeableConcept] = None
    subject: Optional[FHIRReference] = None
    effectiveDateTime: Optional[str] = None
    valueQuantity: Optional[FHIRQuantity] = None
    # Additional metadata
    upload_id: Optional[str] = None
    role_entity_id: Optional[str] = None
    created_at: Optional[datetime] = None
    patient_key: Optional[str] = None  # Key to link to patient


class FHIREncounterClass(BaseModel):
    system: Optional[str] = None
    code: Optional[str] = None
    display: Optional[str] = None


class FHIREncounterLocation(BaseModel):
    location: Optional[FHIRReference] = None


class FHIREncounter(BaseModel):
    resourceType: str = "Encounter"
    id: str
    meta: Optional[FHIRMeta] = None
    identifier: List[FHIRIdentifier] = Field(default_factory=list)
    status: Optional[str] = None
    class_: Optional[FHIREncounterClass] = Field(None, alias="class")
    type: List[FHIRCodeableConcept] = Field(default_factory=list)
    subject: Optional[FHIRReference] = None
    period: Optional[FHIRPeriod] = None
    reasonCode: List[FHIRCodeableConcept] = Field(default_factory=list)
    location: List[FHIREncounterLocation] = Field(default_factory=list)
    # Additional metadata
    upload_id: Optional[str] = None
    role_entity_id: Optional[str] = None
    created_at: Optional[datetime] = None
    patient_key: Optional[str] = None  # Key to link to patient


class FHIRProcedurePerformer(BaseModel):
    actor: Optional[FHIRReference] = None


class FHIRProcedure(BaseModel):
    resourceType: str = "Procedure"
    id: str
    meta: Optional[FHIRMeta] = None
    identifier: List[FHIRIdentifier] = Field(default_factory=list)
    status: Optional[str] = None
    subject: Optional[FHIRReference] = None
    code: Optional[FHIRCodeableConcept] = None
    performedDateTime: Optional[str] = None
    reasonCode: List[FHIRCodeableConcept] = Field(default_factory=list)
    performer: List[FHIRProcedurePerformer] = Field(default_factory=list)
    # Additional metadata
    upload_id: Optional[str] = None
    role_entity_id: Optional[str] = None
    created_at: Optional[datetime] = None
    patient_key: Optional[str] = None  # Key to link to patient


class FileUploadRequest(BaseModel):
    role_entity_id: str
    file_name: str
    file_type: str
    content_type: str


class FileUploadResponse(BaseModel):
    upload_id: str
    status: UploadStatus
    presigned_url: Optional[str] = None
    message: str


class ProcessFileRequest(BaseModel):
    upload_id: str
    role_entity_id: str


class ProcessFileResponse(BaseModel):
    upload_id: str
    status: UploadStatus
    resource_counts: Dict[str, int] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    message: str


class FHIRConversionListResponse(BaseModel):
    conversions: List[FHIRConversionStatus]
    total: int
