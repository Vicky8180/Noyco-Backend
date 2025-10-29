"""
Pydantic schemas for admin routes (if/when needed).

The current admin endpoints return plain dicts assembled from MongoDB
documents and external services to keep flexibility. If you want stricter
validation, add BaseModel classes here and use response_model in routes.
"""

