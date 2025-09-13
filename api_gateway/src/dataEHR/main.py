"""
DataEHR Module for Healthcare Platform API Gateway

This module handles EHR data integration including:
- Conversion of unstructured clinical data to FHIR format
- Integration with Google Healthcare NLP API
- Storage of FHIR resources in MongoDB
- FHIR resource management and querying

The module integrates with the authentication system and provides
role-based access control for hospital data management.
"""

from .routes import router
from .controller import FHIRCSVProcessor
from .schema import (
    FHIRResourceType,
    UploadStatus,
    FileUploadRequest,
    FileUploadResponse,
    ProcessFileRequest,
    ProcessFileResponse,
    FHIRConversionStatus,
    FHIRConversionListResponse,
    FHIRPatient,
    FHIRCondition,
    FHIRObservation,
    FHIREncounter,
    FHIRProcedure
)
from socketio import AsyncServer
# from .fetchController import get_all_patients

__all__ = [
    "router",
    "FHIRCSVProcessor",
    "FHIRResourceType",
    "UploadStatus",
    "FileUploadRequest",
    "FileUploadResponse",
    "ProcessFileRequest",
    "ProcessFileResponse",
    "FHIRConversionStatus",
    "FHIRConversionListResponse",
    "FHIRPatient",
    "FHIRCondition",
    "FHIRObservation",
    "FHIREncounter",
    "FHIRProcedure"
]

# You must have an instance of your Socket.IO server somewhere in your backend.
# For example, if you use FastAPI with python-socketio:
# sio = AsyncServer(async_mode='asgi')

# @sio.on('fetch_all_patients')
# async def handle_fetch_all_patients(sid):
#     patients = get_all_patients()
#     await sio.emit('all_patients_data', patients, to=sid)
