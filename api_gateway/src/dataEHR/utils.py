import uuid
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

def generate_resource_id(resource_type: str) -> str:
    """Generate a unique ID for a FHIR resource"""
    return f"{resource_type.lower()}-{str(uuid.uuid4())}"

def format_fhir_date(date_obj: datetime) -> str:
    """Format a datetime object as a FHIR date string"""
    return date_obj.strftime("%Y-%m-%d")

def format_fhir_datetime(date_obj: datetime) -> str:
    """Format a datetime object as a FHIR datetime string"""
    return date_obj.isoformat()

def create_fhir_reference(resource_type: str, resource_id: str) -> Dict[str, str]:
    """Create a FHIR reference object"""
    return {
        "reference": f"{resource_type}/{resource_id}"
    }

def extract_id_from_reference(reference: str) -> Optional[str]:
    """Extract the ID part from a FHIR reference string"""
    if not reference or '/' not in reference:
        return None
    return reference.split('/')[-1]

def create_fhir_coding(system: str, code: str, display: Optional[str] = None) -> Dict[str, str]:
    """Create a FHIR coding object"""
    coding = {
        "system": system,
        "code": code
    }
    if display:
        coding["display"] = display
    return coding

def create_fhir_codeable_concept(coding_list: List[Dict[str, str]], text: Optional[str] = None) -> Dict[str, Any]:
    """Create a FHIR CodeableConcept object"""
    concept = {
        "coding": coding_list
    }
    if text:
        concept["text"] = text
    return concept

def validate_fhir_resource(resource: Dict[str, Any], resource_type: str) -> List[str]:
    """Validate a FHIR resource against basic requirements"""
    errors = []
    
    # Check resource type
    if resource.get("resourceType") != resource_type:
        errors.append(f"Resource type mismatch: expected {resource_type}, got {resource.get('resourceType')}")
    
    # Check required fields
    required_fields = ["id"]
    if resource_type != "Patient":
        required_fields.append("subject")
    
    for field in required_fields:
        if field not in resource:
            errors.append(f"Missing required field: {field}")
    
    return errors

def sanitize_fhir_resource(resource: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize a FHIR resource for storage"""
    # Create a deep copy to avoid modifying the original
    sanitized = json.loads(json.dumps(resource))
    
    # Remove MongoDB _id if present
    if "_id" in sanitized:
        del sanitized["_id"]
    
    return sanitized 
