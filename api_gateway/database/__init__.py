# API Gateway Configuration Package
# Note: db.py imports get_settings dynamically to avoid circular imports
from .db import get_database, DatabaseConnection

__all__ = ["get_database", "DatabaseConnection"]
