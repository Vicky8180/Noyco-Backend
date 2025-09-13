from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class OCRJobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class OCRJobResponse(BaseModel):
    job_id: str
    status: OCRJobStatus
    filename: str
    text_content: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class OCRJobListResponse(BaseModel):
    jobs: List[OCRJobResponse]
    total: int
    page: int
    per_page: int

class OCRResultResponse(BaseModel):
    job_id: str
    filename: str
    text_content: str
    created_at: datetime

class OCRErrorResponse(BaseModel):
    detail: str
    status_code: int 
