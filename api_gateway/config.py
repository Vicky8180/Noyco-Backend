from pydantic_settings import BaseSettings
from typing import Optional

class APIGatewaySettings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"
    
    # Security - JWT
    JWT_SECRET_KEY: str
    JWT_PRIVATE_KEY_PATH: str = "./keys/private_key.pem"
    JWT_PUBLIC_KEY_PATH: str = "./keys/public_key.pem"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Security - CSRF
    CSRF_SECRET_KEY: str
    CSRF_COOKIE_SECURE: bool = False
    CSRF_COOKIE_HTTPONLY: bool = False
    CSRF_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Cookie settings
    COOKIE_SECURE: bool = False
    COOKIE_DOMAIN: str = "localhost"
    COOKIE_SAMESITE: str = "lax"
    
    # Database connections
    MONGODB_URI: str
    DATABASE_NAME: str = "conversionalEngine"
    REDIS_URL: str = "redis://localhost:6379"
    
    # Service URLs
    ORCHESTRATOR_URL: str = "http://localhost:8002"
    ORCHESTRATOR_ENDPOINT: str = "http://localhost:8002/orchestrate"
    MEMORY_URL: str = "http://localhost:8010"
    DETECTOR_URL: str = "http://localhost:8014"
    CHECKPOINT_URL: str = "http://localhost:8003"
    
    # CORS settings
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    
    # API Keys
    GEMINI_API_KEY: str
    
    # Twilio
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_PHONE_NUMBER: str
    
    # Host URL
    HOST_URL: str
    
    # Google Cloud
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    GOOGLE_CLOUD_PROJECT: Optional[str] = None
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    GOOGLE_HEALTHCARE_DATASET: Optional[str] = None
    
    # Stripe
    STRIPE_SECRET_KEY: str
    STRIPE_PUBLISHABLE_KEY: str
    STRIPE_WEBHOOK_SECRET: str
    STRIPE_SUCCESS_URL: str = "http://localhost:3000/stripe/success"
    STRIPE_CANCEL_URL: str = "http://localhost:3000/stripe/cancel"
    
    # Stripe Price IDs
    PRICE_HOSP_LITE_MONTHLY: str
    PRICE_HOSP_LITE_YEARLY: str
    PRICE_HOSP_PRO_MONTHLY: str
    PRICE_HOSP_PRO_YEARLY: str
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
    TTS_ENGINE: str = "elevenlabs"
    STT_ENGINE: str = "deepgram"
    LLM_ENGINE: str = "gemini-2.0-flash"
    
    # Engine API Keys
    ELEVENLABS_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    DEEPGRAM_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    
    # SMTP
    SMTP_GMAIL_USER: Optional[str] = None
    SMTP_GMAIL_PASS: Optional[str] = None
    
    # Server Configuration
    SERVICE_NAME: str = "api-gateway"
    SERVICE_VERSION: str = "1.0.0"
    SERVICE_HOST: str = "0.0.0.0"
    SERVICE_PORT: int = 8000
    
    # CORS Configuration
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: str = "GET,POST,PUT,DELETE,OPTIONS"
    CORS_ALLOW_HEADERS: str = "Content-Type,Authorization,X-CSRF-Token,X-Requested-With"
    CORS_EXPOSE_HEADERS: str = "X-CSRF-Token"
    CORS_MAX_AGE: int = 86400
    
    # Host URL
    HOST_URL: str

    # Twilio Configuration
    TWILIO_BASE_WEBHOOK_URL: str = "https://53bd327713d2.ngrok-free.app"
    
    # Google Cloud Configuration
    GOOGLE_PROJECT_ID: str = "text-to-speech-464115"
    GOOGLE_CREDENTIALS_PATH: str = "D:/Pap_Anoop/projects/polaris/conversationalEngine/api_gateway/src/phone/google-credentials.json"
    
    # Audio Configuration
    AUDIO_SAMPLE_RATE: int = 8000
    
    # JWT Token Configuration
    JWT_ACCESS_TOKEN_COOKIE_NAME: str = "access_token"
    JWT_REFRESH_TOKEN_COOKIE_NAME: str = "refresh_token"
    JWT_CSRF_COOKIE_NAME: str = "csrf_token"
    JWT_ALGORITHM: str = "RS256"
    
    # Default Admin Configuration
    DEFAULT_ADMIN_EMAIL: str = "admin@Noyco.local"
    DEFAULT_ADMIN_PASSWORD: str = "Admin123!"
    
    # OTP Configuration
    OTP_TTL: int = 10
    
    # MongoDB Configuration (additional)
    MONGO_URI: str = ""  # Fallback field
    MONGO_DB: str = "Noyco"  # Fallback field
    
    # SocketIO Configuration
    SOCKETIO_CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    SOCKETIO_LOGGER: bool = True
    SOCKETIO_ENGINEIO_LOGGER: bool = True
    
    # LiveKit TTL Configuration
    LIVEKIT_TTL_MINUTES: int = 120
    
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
