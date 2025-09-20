# api_gateway/main.py
"""
Healthcare Platform API Gateway
Minimal main file with core FastAPI setup and routing
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import socketio
import uvicorn
import logging
import warnings
from datetime import datetime

# Configure logging to reduce verbosity
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)
logging.getLogger("engineio.server").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

# Suppress pydantic warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", module="pydantic")

# This block allows running the script directly while maintaining relative imports
if __name__ == "__main__" and __package__ is None:
    import sys
    from os import path
    sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
    # The following imports are now relative to the project root
    from api_gateway.config import get_settings
    from api_gateway.middlewares.jwt_auth_middleware import JWTAuthMiddleware
    from api_gateway.socketio_server import create_socketio_server
    # from api_gateway.router_config import setup_routers, initialize_schedule_controller
    from api_gateway.router_config import setup_routers
    from api_gateway.health_monitor import HealthMonitor
else:
    # Core imports
    from .config import get_settings
    from .middlewares.jwt_auth_middleware import JWTAuthMiddleware
    from .socketio_server import create_socketio_server
    # from .router_config import setup_routers, initialize_schedule_controller
    from .router_config import setup_routers
    from .health_monitor import HealthMonitor

# Get settings
settings = get_settings()
allowed_origins = settings.ALLOWED_ORIGINS.split(",")

# Create and configure Socket.IO server
sio, socket_handlers = create_socketio_server(allowed_origins)

# Initialize health monitor
health_monitor = HealthMonitor(settings)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup
    await health_monitor.startup_health_display()
    # Initialize schedule controller
    # await initialize_schedule_controller()
    
    yield

# Create FastAPI app
app = FastAPI(
    title="Healthcare Platform API Gateway with Call Interface",
    description="Authentication, routing gateway, real-time call interface, and FHIR data integration for healthcare microservices",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS.split(","),
    allow_headers=settings.CORS_ALLOW_HEADERS.split(","),
    expose_headers=settings.CORS_EXPOSE_HEADERS.split(","),
    max_age=settings.CORS_MAX_AGE,
)

# Add JWT authentication middleware
app.add_middleware(JWTAuthMiddleware)

# Setup all application routers
app = setup_routers(app)

# Wrap FastAPI app with Socket.IO
socket_app = socketio.ASGIApp(sio, app)



# Core API endpoints
@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "healthy", "service": "api_gateway_with_call_interface"}

@app.get("/health/services")
async def comprehensive_health_check():
    """Comprehensive health check for all microservices using HealthMonitor"""
    return await health_monitor.comprehensive_health_check()

@app.get("/")
async def root():
    """Root endpoint with platform information"""
    return {
        "message": "Healthcare Platform API Gateway with Call Interface",
        "version": "1.0.0",
        "features": ["authentication", "routing", "billing", "real-time_calls", "socket_io", "fhir_data_conversion", "mediscan_ocr"]
    }

# Call Interface API Endpoints
@app.post("/api/call")
async def trigger_call():
    """Endpoint to trigger a call popup on frontend"""
    try:
        print("Triggering call...")
        call_data = {
            "callId": f"call_{datetime.now().timestamp()}",
            "caller": "John Doe",
            "callerNumber": "+1 234 567 8900",
            "timestamp": datetime.now().isoformat(),
            "type": "incoming"
        }

        # Use socket handlers to emit the call event
        await socket_handlers.trigger_incoming_call(call_data)

        return {
            "success": True,
            "message": "Call triggered successfully",
            "callData": call_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/calls/active")
async def get_active_calls():
    """Get all active calls"""
    return socket_handlers.get_active_calls()

# Main entry point
if __name__ == "__main__":
    uvicorn.run(socket_app, host=settings.SERVICE_HOST, port=settings.SERVICE_PORT, log_level="info")
