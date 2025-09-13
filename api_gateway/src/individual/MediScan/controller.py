from fastapi import HTTPException, status
from typing import List
import uuid
from datetime import datetime
from pymongo import UpdateOne, errors

from ...patients.schema import Patient
from api_gateway.database.db import get_database


class PatientInteractioController:
    """Controller for patient management"""

    def __init__(self):
        self.db = get_database()
        self.patients_collection = self.db.patients
        self._create_indexes()

    def _create_indexes(self):
        try:
            bulk_ops = []
            cursor = self.patients_collection.find(
                {"$or": [{"id": {"$exists": False}}, {"id": None}]},
                {"_id": 1}
            )
            for doc in cursor:
                bulk_ops.append(
                    UpdateOne(
                        {"_id": doc["_id"]},
                        {"$set": {"id": f"patient-{uuid.uuid4()}"}},
                        upsert=False
                    )
                )
            if bulk_ops:
                self.patients_collection.bulk_write(bulk_ops)

            self.patients_collection.create_index("id", unique=True, sparse=True)
            self.patients_collection.create_index("owner_id")
            self.patients_collection.create_index("name")
            self.patients_collection.create_index("medical_record_number")
            self.patients_collection.create_index("status")
        except errors.DuplicateKeyError as dup_err:
            print(f"[Patients] Duplicate key error while creating index: {dup_err}")
        except Exception as e:
            print(f"Error creating indexes: {str(e)}")

    async def get_patients_by_owner_id(self, owner_id: str) -> List[Patient]:
        """Fetch all patients for a given owner"""
        patients_cursor = self.patients_collection.find({"owner_id": owner_id})
        patients_list = list(patients_cursor)[:100]
        if not patients_list:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No patients found for the specified owner_id"
            )
        return [Patient(**patient) for patient in patients_list]
