# from pydantic_settings import BaseSettings
# from typing import Optional

# class PrimarySettings(BaseSettings):
#     # Environment
#     ENVIRONMENT: str = "development"
    
#     # Database connections
#     MONGODB_URI: str
#     DATABASE_NAME: str 
#     REDIS_URL: str 
    
#     # API Keys
#     GEMINI_API_KEY: str
#     GOOGLE_API_KEY: Optional[str] 
    
#     # Google Cloud
#     GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
#     GOOGLE_CLOUD_PROJECT: Optional[str] = None
#     GOOGLE_CLOUD_LOCATION: str = "us-central1"
#     GOOGLE_HEALTHCARE_DATASET: Optional[str] = None
    
#     # Engine choices
#     LLM_ENGINE: str = "gemini-2.0-flash"
    
#     # Service Configuration
#     SERVICE_NAME: str = "primary"
#     SERVICE_VERSION: str = "1.0.0"
#     PRIMARY_SERVICE_PORT: int = 8004
#     PRIMARY_SERVICE_HOST: str = "0.0.0.0"
    
#     # Service URLs
#     PRIMARY_SERVICE_URL: Optional[str] = "http://localhost:8004/process"
    
#     class Config:
#         env_file = ".env"
#         case_sensitive = True
#         extra = "allow"  # Allow extra fields from .env that this service doesn't use

# def get_settings() -> PrimarySettings:
#     return PrimarySettings()
