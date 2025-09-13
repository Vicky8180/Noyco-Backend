
import os
import io
import json
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, UploadFile, status

# Remove Google Healthcare NLP
from google.cloud import vision
from google.oauth2 import service_account

# Add Gemini imports
import google.generativeai as genai
from google.api_core import retry

# Patient management
# Adjust relative import (three dots to reach src)
from ...patients.controller import PatientController
from ...patients.schema import (
    OwnerType,
    Gender,
    VisitStatus,
    Prescription,
    LabResult,
    Condition,
    Allergy,
    Visit,
)
import fitz  # PyMuPDF for PDF processing
from datetime import datetime
from api_gateway.database.db import get_database
from ....utils.helperFunctions import generate_unique_id
import asyncio



# Add this class at the top of your file with the other imports
class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for handling datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super(DateTimeEncoder, self).default(obj)


class OCRController:
    """Controller for handling OCR processing with Google Cloud Vision API and Gemini"""
    
    def __init__(self):
        self.db = get_database()
 
        # Initialize collections
        # NOTE: We no longer persist raw OCR jobs/results. Collections kept for backward
        # compatibility but not used in new pipeline.
        self.ocr_results = self.db.ocr_results  # legacy – not used
        self.ocr_jobs = self.db.ocr_jobs        # legacy – not used

        # Services
        self.patient_controller = PatientController()
 
        # Initialize Google Cloud Vision client
        self._init_vision_client()

        # Initialize Gemini client for medical text analysis
        self._init_gemini_client()
        
    def _init_vision_client(self):
        """Initialize Google Cloud Vision client with credentials"""
        try:
            # Try multiple possible paths for credentials file
            possible_paths = [
                # Path 1: Root level keys directory
                os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
                    "keys",
                    "google-cloudvision-credentials.json"
                ),
                # Path 2: API gateway level keys directory
                os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                    "keys",
                    "google-cloudvision-credentials.json"
                ),
                # Path 3: Absolute path based on current working directory
                os.path.join(
                    os.getcwd(),
                    "conversionalEngine",
                    "keys",
                    "google-cloudvision-credentials.json"
                ),
                # Path 4: Another absolute path option
                os.path.join(
                    os.getcwd(),
                    "conversionalEngine",
                    "api_gateway",
                    "keys",
                    "google-cloudvision-credentials.json"
                )
            ]
            
            credentials_path = None
            for path in possible_paths:
                print(f"Checking for credentials at: {path}")
                if os.path.exists(path):
                    credentials_path = path
                    print(f"Found credentials at: {path}")
                    break
            
            if not credentials_path:
                raise FileNotFoundError(f"Credentials file not found at any of the expected locations: {possible_paths}")
                
            # Initialize client with credentials
            self.credentials = service_account.Credentials.from_service_account_file(credentials_path)
            self.vision_client = vision.ImageAnnotatorClient(credentials=self.credentials)
            print("Successfully initialized Google Cloud Vision client")
            
        except Exception as e:
            print(f"Error initializing Google Cloud Vision client: {str(e)}")
            self.vision_client = None

    # ------------------------------------------------------------------
    # Gemini Text Analysis
    # ------------------------------------------------------------------

    def _init_gemini_client(self):
        """Initialize Gemini AI client"""
        try:
            # Try multiple possible paths for credentials file
            possible_paths = [
                # Path 1: Root level keys directory
                os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
                    "keys",
                    "gemini-credentials.json"
                ),
                # Path 2: API gateway level keys directory
                os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                    "keys",
                    "gemini-credentials.json"
                ),
                # Path 3: Environment variable
                os.environ.get("GEMINI_API_KEY")
            ]
            
            api_key = "AIzaSyCklVFWThy-L9Ad4TqQdYNefGF4f206THM"
            # First check for a credentials file
            for path in possible_paths[:2]:
                if os.path.exists(path):
                    print(f"Found Gemini credentials at: {path}")
                    with open(path, "r") as f:
                        creds = json.load(f)
                        api_key = creds.get("api_key")
                    break
                    
            # If no file found, check environment variable
            if not api_key and possible_paths[2]:
                api_key = possible_paths[2]
                
            if not api_key:
                raise ValueError("Gemini API key not found in credentials file or environment variable")
                
            # Configure Gemini
            genai.configure(api_key=api_key)
            
            # Initialize Gemini model
            # Using the most capable model for medical text analysis
            self.gemini_model = genai.GenerativeModel(model_name="gemini-1.5-pro")
            print("Successfully initialized Gemini client")
            
        except Exception as e:
            print(f"Error initializing Gemini client: {str(e)}")
            self.gemini_model = None

    @retry.Retry()
    async def _analyze_medical_text(self, text: str) -> dict:
        """Use Gemini to extract structured medical information from text"""
        if not self.gemini_model:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Gemini AI client not available"
            )

        try:
            prompt = f"""
You are a highly accurate and clinically informed medical data extraction assistant.

Your task is to extract **structured medical information** from the **unstructured prescription or clinical note** provided below. In addition to extracting explicit information, you should **infer missing but clinically relevant details** (such as probable conditions, allergies, or medication notes) **based on context**—but do **not fabricate information that is unsupported** by the text.

Use your medical knowledge to maximize insight, and ensure that **all units, frequencies, and formats** follow **standard clinical conventions** (e.g., use "mg", "ml", "once daily", "every 8 hours", etc.).

Your output must be a single valid JSON object containing the following fields:

---

1. **"diagnosis"**: The main clinical diagnosis or assessment (string)

2. **"chief_complaint"**: The primary symptom or reason for the visit (string)

3. **"medications"**: A list of medications with full details, each with:
   - `"medication"`: Name of the drug (string)
   - `"dosage"`: Strength (e.g., "500mg", "10ml") (string)
   - `"frequency"`: How often it should be taken (e.g., "once daily", "every 8 hours") (string)
   - `"route"`: Route of administration (e.g., "oral", "IV", "topical") (string)
   - `"duration"`: Duration of use (e.g., "5 days", "as needed") (string)
   - `"notes"`: Clinical purpose or special instructions for this drug (string)

4. **"lab_results"**: Any lab results mentioned, each with:
   - `"test_name"`: Name of the test (string)
   - `"test_code"`: Test code, if known (string)
   - `"value"`: Observed value (string)
   - `"unit"`: Measurement unit (string)
   - `"reference_range"`: Normal or reference range (string)
   - `"is_abnormal"`: `true` if result is abnormal, else `false` (boolean)
   - `"notes"`: Interpretation or remarks (string)

5. **"conditions"**: Inferred or stated medical conditions, each with:
   - `"name"`: Name of the condition (string)
   - `"icd_code"`: ICD-10 code, if known (string)
   - `"status"`: One of: `"active"`, `"resolved"`, `"chronic"`, `"inactive"` (string)
   - `"onset_date"`: Onset date if known or estimated (YYYY-MM-DD format) (string)
   - `"notes"`: Reasoning, context, or relevant details (string)

6. **"allergies"**: Known or suspected allergies, each with:
   - `"substance"`: Allergen (e.g., "Penicillin") (string)
   - `"reaction"`: Reaction description (string)
   - `"severity"`: One of: `"mild"`, `"moderate"`, `"severe"` (string)
   - `"notes"`: Source or reasoning (e.g., "reported by patient", "inferred from drug history") (string)

7. **"visit_notes"**: Concise summary of clinical notes, impressions, or relevant observations (string)

---

**Additional Rules:**
- Use **standard clinical terminology** and maintain **unit consistency** across entries.
- Be **conservative in your inferences**: infer only what is medically justified by context.
- Leave fields blank or empty ("" / []) if information is not available or cannot be reasonably inferred.

Now, process the following medical text:

Input:
\"\"\"
{text}
\"\"\"
"""

            # Create a response using Gemini
            response = await asyncio.to_thread(
                lambda: self.gemini_model.generate_content(prompt).text
            )
            
            # Parse the JSON from response
            try:
                # Remove any markdown formatting if present
                json_text = response.strip()
                if json_text.startswith("```json"):
                    json_text = json_text[7:]
                if json_text.endswith("```"):
                    json_text = json_text[:-3]
                
                json_text = json_text.strip()
                return json.loads(json_text)
            except json.JSONDecodeError as e:
                print(f"Error parsing Gemini response as JSON: {e}")
                print(f"Raw response: {response}")
                # Return a minimal valid structure if parsing fails
                return {
                    "diagnosis": "",
                    "chief_complaint": "",
                    "medications": [],
                    "lab_results": [],
                    "conditions": [],
                    "allergies": [],
                    "visit_notes": "Error parsing medical data"
                }
                
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gemini analysis error: {e}"
            )

    # ------------------------------------------------------------------
    # Patient conversion helpers
    # ------------------------------------------------------------------

    def _convert_gemini_to_patient_dict(self, gemini_response: dict, owner_id: str) -> dict:
        """Convert Gemini structured output to Patient schema-compatible dict"""

        # Build prescriptions from medications
        prescriptions = []
        for med in gemini_response.get("medications", []):
            prescriptions.append(Prescription(
                medication=med.get("medication", "") or "",
                dosage=med.get("dosage", "") or "",
                frequency=med.get("frequency", "") or "",
                route=med.get("route", "") or "oral",
                duration=med.get("duration", "") or "",
                notes=med.get("notes", "") or ""
            ).dict())

        # Build lab results
        lab_results = []
        for lab in gemini_response.get("lab_results", []):
            lab_results.append(LabResult(
                test_name=lab.get("test_name", "") or "",
                test_code=lab.get("test_code", "") or "",
                value=lab.get("value", "") or "",
                unit=lab.get("unit", "") or "",
                reference_range=lab.get("reference_range", "") or "",
                is_abnormal=lab.get("is_abnormal", False) if lab.get("is_abnormal") is not None else False,
                notes=lab.get("notes", "") or ""
            ).dict())

        # Build conditions
        conditions = []
        for condition in gemini_response.get("conditions", []):
            # Convert onset_date string to datetime if present
            onset_date = None
            if condition.get("onset_date"):
                try:
                    onset_date = datetime.fromisoformat(condition.get("onset_date"))
                except (ValueError, TypeError):
                    onset_date = None
            
            conditions.append(Condition(
                name=condition.get("name", "") or "",
                icd_code=condition.get("icd_code", "") or "",
                status=condition.get("status", "") or "active",
                onset_date=onset_date,
                notes=condition.get("notes", "") or ""
            ).dict())

        # Build allergies
        allergies = []
        for allergy in gemini_response.get("allergies", []):
            allergies.append(Allergy(
                substance=allergy.get("substance", "") or "",
                reaction=allergy.get("reaction", "") or "",
                severity=allergy.get("severity", "") or "mild",
                notes=allergy.get("notes", "") or ""
            ).dict())

        # Create visit
        visit = Visit(
            id=generate_unique_id("visit"),
            visit_date=datetime.utcnow(),
            diagnosis=gemini_response.get("diagnosis", "") or "",
            visit_notes=(gemini_response.get("chief_complaint", "") or gemini_response.get("visit_notes", "")) or "",
            prescriptions=prescriptions,
            lab_results=lab_results,
            conditions=conditions,
            allergies=allergies,
            status=VisitStatus.COMPLETED,
        ).dict()

        # Create patient dict
        patient_dict = {
            "name": "Unknown Patient",  # Placeholder – could be enhanced with demographic extraction
            "gender": Gender.UNKNOWN,
            "owner_type": OwnerType.INDIVIDUAL,
            "owner_id": owner_id,
            "visits": [visit],
        }

        return patient_dict
    async def process_document(self, file: UploadFile, owner_id: str, patient_id: Optional[str] = None) -> Dict[str, Any]:
        """Process a document with OCR and Gemini analysis"""
        if not self.vision_client:
            # Try to initialize the client again
            self._init_vision_client()
        
            if not self.vision_client:
                # If still not available, raise an error with more details
                credentials_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
                    "keys",
                    "google-cloudvision-credentials.json"
                )
            
                exists = os.path.exists(credentials_path)
            
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"OCR service is not available. Credentials file exists: {exists}, Path: {credentials_path}"
                )
        
        try:
            # Read file bytes
            file_content = await file.read()
            file_extension = os.path.splitext(str(file.filename or ""))[1].lower()

            # ---------------- OCR ----------------
            # Process based on file type
            if file_extension == '.pdf':
                text_content = await self._process_pdf(file_content, "tmp")
            else:  # Image files
                text_content = await self._process_image(file_content, "tmp")

            # ---------------- Gemini Analysis ----------------
            print(f"Extracted text content length: {len(text_content)}")
            gemini_response = await self._analyze_medical_text(text_content)
            print("Gemini analysis response:", json.dumps(gemini_response, indent=2))

            # Convert Gemini response to patient data structure
            patient_data = self._convert_gemini_to_patient_dict(gemini_response, owner_id)
            # Use the DateTimeEncoder for JSON serialization
            print("Converted patient data:", json.dumps(patient_data, indent=2, cls=DateTimeEncoder))

            # ---------------- Persist / Update Patient ----------------
            if patient_id:
                # Update existing patient – fill missing demographics and add new visit
                existing_patient = await self.patient_controller.get_patient(patient_id)
                if not existing_patient:
                    raise HTTPException(status_code=404, detail="Patient not found")

                # Prepare demographic updates only if they are unknown / placeholder
                demo_update = {}
                for field in ["name", "gender"]:
                    if getattr(existing_patient, field, None) in [None, "Unknown Patient", "unknown"] and patient_data.get(field):
                        demo_update[field] = patient_data[field]

                # Always add visit from OCR
                if patient_data.get("visits"):
                    await self.patient_controller.add_visit(patient_id, patient_data["visits"][0])

                if demo_update:
                    await self.patient_controller.update_patient(patient_id, demo_update)

                updated_patient = await self.patient_controller.get_patient(patient_id)

                if not updated_patient:
                    raise HTTPException(status_code=500, detail="Failed to retrieve updated patient")

                return {
                    "status": "success",
                    "message": "Document processed and patient record updated",
                    "patient": updated_patient.dict() if hasattr(updated_patient, 'dict') else updated_patient,
                }
            else:
                # Create new patient if no patient_id provided
                created_patient = await self.patient_controller.create_patient(patient_data)

                return {
                    "status": "success",
                    "message": "Document processed and patient record created",
                    "patient": created_patient.dict() if hasattr(created_patient, 'dict') else created_patient,
                }
        
        except Exception as e:
            # Log the full error
            import traceback
            print(f"Error processing document: {str(e)}")
            print(traceback.format_exc())
        
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing document: {str(e)}"
            )
    async def _process_pdf(self, file_content: bytes, job_id: str) -> str:
        """Process a PDF document with OCR"""
        try:
            # Save PDF to a temporary file
            temp_file_path = f"/tmp/{job_id}.pdf"
            with open(temp_file_path, "wb") as temp_file:
                temp_file.write(file_content)
                
            # Open the PDF with PyMuPDF
            pdf_document = fitz.open(temp_file_path)
            
            all_text = []
            
            # Process each page
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                
                # First try to extract text directly (if PDF has embedded text)
                page_text = page.get_text()
                
                # If minimal text found, use OCR
                if len(page_text.strip()) < 50:
                    # Convert PDF page to image
                    pix = page.get_pixmap(alpha=False)
                    img_bytes = pix.tobytes("png")
                    
                    # Process image with Vision API
                    image = vision.Image(content=img_bytes)
                    response = self.vision_client.text_detection(image=image)
                    
                    if response.error.message:
                        raise Exception(f"Error detecting text: {response.error.message}")
                        
                    # Extract text
                    if response.text_annotations:
                        page_text = response.text_annotations[0].description
                
                all_text.append(f"--- Page {page_num + 1} ---\n{page_text}")
                    
            # Clean up
            pdf_document.close()
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                
            return "\n\n".join(all_text)
            
        except Exception as e:
            raise Exception(f"Error processing PDF: {str(e)}")
            
    async def _process_image(self, file_content: bytes, job_id: str) -> str:
        """Process an image with OCR"""
        try:
            # Create image object
            image = vision.Image(content=file_content)
            
            # Perform text detection
            print(f"Sending image to Google Cloud Vision API for job {job_id}")
            response = self.vision_client.text_detection(image=image)
            
            if response.error and response.error.message:
                error_msg = f"Error detecting text: {response.error.message}"
                print(error_msg)
                raise Exception(error_msg)
                
            # Extract text
            if response.text_annotations and len(response.text_annotations) > 0:
                text = response.text_annotations[0].description
                print(f"Successfully extracted {len(text)} characters of text for job {job_id}")
                return text
            else:
                print(f"No text detected in the image for job {job_id}")
                return "No text detected in the image."
                
        except Exception as e:
            error_msg = f"Error processing image: {str(e)}"
            print(error_msg)
            raise Exception(error_msg)
            
    async def get_ocr_job(self, job_id: str, user_id: str) -> Dict[str, Any]:
        """Get OCR job status and result"""
        try:
            # Find job record
            job = self.ocr_jobs.find_one({"id": job_id, "user_id": user_id})
            
            if not job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="OCR job not found"
                )
                
            # If job is completed, get the result
            result = None
            if job["status"] == "completed":
                result_record = self.ocr_results.find_one({"job_id": job_id})
                if result_record:
                    result = {
                        "id": result_record["id"],
                        "text_content": result_record["text_content"]
                    }
                    
            return {
                "job_id": job["id"],
                "status": job["status"],
                "filename": job["filename"],
                "created_at": job["created_at"],
                "updated_at": job["updated_at"],
                "result": result
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving OCR job: {str(e)}"
            )
            
    async def get_user_jobs(self, user_id: str, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all OCR jobs for a user"""
        try:
            # Find all jobs for the user
            cursor = self.ocr_jobs.find({"user_id": user_id}).sort("created_at", -1).skip(offset).limit(limit)
            
            jobs = []
            for job in cursor:
                jobs.append({
                    "job_id": job["id"],
                    "status": job["status"],
                    "filename": job["filename"],
                    "created_at": job["created_at"],
                    "updated_at": job["updated_at"]
                })
                
            return jobs
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving OCR jobs: {str(e)}"
            )
