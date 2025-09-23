from pydantic_settings import BaseSettings
from typing import Optional

class APIGatewaySettings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"
    
    # Security - JWT
    JWT_SECRET_KEY: str
    JWT_PRIVATE_KEY_PATH: str 
    JWT_PUBLIC_KEY_PATH: str 
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int 
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int 
    
    # Security - CSRF
    CSRF_SECRET_KEY: str
    CSRF_COOKIE_SECURE: bool 
    CSRF_COOKIE_HTTPONLY: bool 
    CSRF_TOKEN_EXPIRE_MINUTES: int 
    
    # Cookie settings
    COOKIE_SECURE: bool 
    COOKIE_DOMAIN: str 
    COOKIE_SAMESITE: str 
    
    # Database connections
    MONGODB_URI: str
    DATABASE_NAME: str 
    REDIS_URL: str 
    
    # Service URLs
    ORCHESTRATOR_URL: str
    MEMORY_URL: str 
    CHECKPOINT_URL: str
    DETECTOR_URL: Optional[str] = None
    PRIMARY_SERVICE_URL: str
    
    # Agent Service URLs
    CHECKLIST_SERVICE_URL: str
    PRIVACY_SERVICE_URL: Optional[str] = None
    NUTRITION_SERVICE_URL: Optional[str] = None
    FOLLOWUP_SERVICE_URL: Optional[str] = None
    HISTORY_SERVICE_URL: Optional[str] = None
    HUMAN_INTERVENTION_SERVICE_URL: Optional[str] = None
    MEDICATION_SERVICE_URL: Optional[str] = None
    
    # Specialized Agent Services
    LONELINESS_SERVICE_URL: str
    ACCOUNTABILITY_SERVICE_URL: str
    THERAPY_SERVICE_URL: str
    EMOTIONAL_SERVICE_URL: Optional[str] = None
    ANXIETY_SERVICE_URL: Optional[str] = None
    
    # Service Port Configuration (for health checks)
    PRIMARY_SERVICE_PORT: Optional[int] = 8002
    CHECKLIST_SERVICE_PORT: Optional[int] = 8002
    AGENTS_SERVICE_PORT: Optional[int] = 8015
    
    # CORS settings
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    
    # API Keys
    GEMINI_API_KEY: str
    
    # Twilio
    # TWILIO_ACCOUNT_SID: str
    # TWILIO_AUTH_TOKEN: str
    # TWILIO_PHONE_NUMBER: str
    
    # Host URL
    HOST_URL: str
    
    # Google Cloud
    # GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    # GOOGLE_CLOUD_PROJECT: Optional[str] = None
    # GOOGLE_CLOUD_LOCATION: str = "us-central1"
    # GOOGLE_HEALTHCARE_DATASET: Optional[str] = None
    
    # Stripe
    STRIPE_SECRET_KEY: str
    STRIPE_PUBLISHABLE_KEY: str
    STRIPE_WEBHOOK_SECRET: str
    STRIPE_SUCCESS_URL: str 
    STRIPE_CANCEL_URL: str 
    
    # Stripe Price IDs
    # PRICE_HOSP_LITE_MONTHLY: str
    # PRICE_HOSP_LITE_YEARLY: str
    # PRICE_HOSP_PRO_MONTHLY: str
    # PRICE_HOSP_PRO_YEARLY: str
    PRICE_IND_LITE_MONTHLY: str
    PRICE_IND_LITE_YEARLY: str
    PRICE_IND_PRO_MONTHLY: str
    PRICE_IND_PRO_YEARLY: str
    
    # Voice Widget
    VOICE_WIDGET_JWT_SECRET: str
    
    # LiveKit
    LIVEKIT_HOST: str
    LIVEKIT_API_KEY: str
    LIVEKIT_API_SECRET: str
    
    # Embed Base URL
    EMBED_BASE_URL: str = "http://localhost:8000"
    
    # Engine choices
    TTS_ENGINE: str 
    STT_ENGINE: str 
    LLM_ENGINE: str 
    
    # Engine API Keys
    ELEVENLABS_API_KEY: Optional[str] 
    OPENAI_API_KEY: Optional[str] 
    DEEPGRAM_API_KEY: Optional[str] 
    GOOGLE_API_KEY: Optional[str] 
    
    # SMTP
    SMTP_GMAIL_USER: Optional[str] 
    SMTP_GMAIL_PASS: Optional[str] 
    
    # Server Configuration
    SERVICE_NAME: str = "api-gateway"
    SERVICE_VERSION: str = "1.0.0"
    SERVICE_HOST: str = "0.0.0.0"
    SERVICE_PORT: int = 8000
    
    # CORS Configuration
    CORS_ALLOW_CREDENTIALS: bool 
    CORS_ALLOW_METHODS: str 
    CORS_ALLOW_HEADERS: str 
    CORS_EXPOSE_HEADERS: str 
    CORS_MAX_AGE: int 
    
    # Host URL
    # HOST_URL: str

    # Twilio Configuration
    # TWILIO_BASE_WEBHOOK_URL: str = "https://53bd327713d2.ngrok-free.app"
    
    # # Google Cloud Configuration
    # GOOGLE_PROJECT_ID: str = "text-to-speech-464115"
    # GOOGLE_CREDENTIALS_PATH: str = "./api_gateway/src/phone/google-credentials.json"
    
    # Audio Configuration
    # AUDIO_SAMPLE_RATE: int = 8000
    
    # JWT Token Configuration
    JWT_ACCESS_TOKEN_COOKIE_NAME: str 
    JWT_REFRESH_TOKEN_COOKIE_NAME: str 
    JWT_CSRF_COOKIE_NAME: str 
    JWT_ALGORITHM: str 
    
    # Default Admin Configuration
    DEFAULT_ADMIN_EMAIL: str = "admin@Noyco.local"
    DEFAULT_ADMIN_PASSWORD: str = "Admin123!"
    
    # OTP Configuration
    OTP_TTL: int = 10
    
    # MongoDB Configuration (additional)
    MONGO_URI: str = ""  # Fallback field
    MONGO_DB: str = "Noyco"  # Fallback field
    
    # SocketIO Configuration
    SOCKETIO_CORS_ORIGINS: str 
    SOCKETIO_LOGGER: bool 
    SOCKETIO_ENGINEIO_LOGGER: bool 
    
    # LiveKit TTL Configuration
    LIVEKIT_TTL_MINUTES: int 
    
    # Default LiveKit Session Values
    DEFAULT_CONVERSATION_ID: str = "livekit_conversation"
    DEFAULT_PLAN: str = "lite"
    DEFAULT_INDIVIDUAL_ID: str = "individual_f068689a7d96"
    DEFAULT_USER_PROFILE_ID: str = "user_profile_610f7db5658e"
    DEFAULT_DETECTED_AGENT: str = "loneliness"
    DEFAULT_AGENT_INSTANCE_ID: str = "loneliness_658"
    DEFAULT_CALL_LOG_ID: str = "call_log_livekit"
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Allow extra fields from .env that this service doesn't use

def get_settings() -> APIGatewaySettings:
    return APIGatewaySettings()
