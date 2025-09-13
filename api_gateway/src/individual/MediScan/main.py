"""
MediScan Module for Healthcare Platform API Gateway

This module provides OCR processing capabilities using Google Cloud Vision API
for individual users to extract text from medical documents.

Features:
- OCR processing of PDF and image files
- Text extraction from medical documents
- Document management for individual users
"""

from .routes import router
from .ocr_controller import OCRController
from .schema import (
    OCRJobStatus,
    OCRJobResponse,
    OCRJobListResponse,
    OCRResultResponse,
    OCRErrorResponse
)

__all__ = [
    "router",
    "OCRController",
    "OCRJobStatus",
    "OCRJobResponse",
    "OCRJobListResponse",
    "OCRResultResponse",
    "OCRErrorResponse"
] 
