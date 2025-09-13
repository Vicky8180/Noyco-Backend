from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime

# ------------------ ENUMS ------------------

#   UserRole enum removed - import from auth.schema if needed

class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"

class OwnerType(str, Enum):
    INDIVIDUAL = "individual"
    ORGANIZATION = "organization"

class AllergySeverity(str, Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"

class ConditionStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    RESOLVED = "resolved"
    CHRONIC = "chronic"

class LabValueType(str, Enum):
    NUMERIC = "numeric"
    TEXT = "text"
    BOOLEAN = "boolean"

class PrescriptionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    DISCONTINUED = "discontinued"
    SUSPENDED = "suspended"

class PatientStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    TRANSFERRED = "transferred"

class VisitStatus(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"

# ------------------ CLINICAL MODELS ------------------

class Allergy(BaseModel):
    substance: str
    reaction: Optional[str] = None
    severity: AllergySeverity = AllergySeverity.MILD
    notes: Optional[str] = None

class Condition(BaseModel):
    name: str
    icd_code: Optional[str] = None  # ICD-10 code for standardization
    status: ConditionStatus = ConditionStatus.ACTIVE
    onset_date: Optional[datetime] = None
    notes: Optional[str] = None

class Prescription(BaseModel):
    medication: str
    dosage: str
    frequency: str
    route: Optional[str] = "oral"  # oral, intravenous, topical, etc.
    duration: Optional[str] = None  # e.g., "7 days", "2 weeks"
    notes: Optional[str] = None

class LabResult(BaseModel):
    test_name: str
    test_code: Optional[str] = None  # Standard lab code (LOINC)
    value: str
    unit: Optional[str] = None
    value_type: LabValueType = LabValueType.TEXT
    reference_range: Optional[str] = None
    is_abnormal: Optional[bool] = None
    notes: Optional[str] = None

# ------------------ VISIT/CONSULTATION MODEL ------------------

class Visit(BaseModel):
    id: str = Field(..., description="Unique visit/consultation ID")
    visit_date: datetime = Field(default_factory=datetime.utcnow)
    diagnosis: Optional[str] = None
    visit_notes: Optional[str] = None
    
    # Clinical data for this visit
    prescriptions: List[Prescription] = []
    lab_results: List[LabResult] = []
    conditions: List[Condition] = []
    allergies: List[Allergy] = []
    
    # Visit status
    status: VisitStatus = VisitStatus.SCHEDULED
    
    # Visit metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# ------------------ PATIENT MODEL ------------------

class Patient(BaseModel):
    patient_id: str = Field(..., description="Unique patient ID")

    # Basic Demographics
    name: str
    gender: Gender
    age: Optional[int] = None
    dob: Optional[datetime] = None
    contact_number: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None

    # Ownership & Access Control (aligned with auth system)
    owner_type: OwnerType
    owner_id: str  # Maps to hospital.id or individual.id from auth system

    # Clinical Information
    medical_record_number: Optional[str] = None
    summary: Optional[str] = Field(None, description="Brief summary of patient's medical history")
    
    # All visits/consultations - each visit contains its own clinical data
    visits: List[Visit] = []
    visit_status: Optional[VisitStatus] = None

    # System fields
    status: PatientStatus = PatientStatus.ACTIVE
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_visit: Optional[datetime] = None

    # Audit trail
    last_modified_by: Optional[str] = None
    last_modified_at: Optional[datetime] = None 
