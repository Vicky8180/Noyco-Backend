"""
Core Service Main Application
Consolidates orchestrator, primary, checkpoint, and checklist services into a single application
with sub-mounted applications accessible via different paths.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    # Import the individual service applications
    from .orchestrator.main import app as orchestrator_app
    from .primary.main import app as primary_app
    from .checkpoint.main import app as checkpoint_app
    from .checklist.main import app as checklist_app
    import_mode = "relative"
except ImportError:
    # Fallback to absolute imports (when run standalone)
    if __name__ == "__main__" and __package__ is None:
        import sys
        from os import path
        sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

        # Import the individual service applications
        from orchestrator.main import app as orchestrator_app
        from primary.main import app as primary_app
        from checkpoint.main import app as checkpoint_app
        from checklist.main import app as checklist_app
        import_mode = "standalone"
    else:
            # Import the individual service applications
        from .orchestrator.main import app as orchestrator_app
        from .primary.main import app as primary_app
        from .checkpoint.main import app as checkpoint_app
        from .checklist.main import app as checklist_app
        import_mode = "module"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for the core service."""
    logger.info("Starting Core Service...")
    yield
    logger.info("Shutting down Core Service...")

# Create the main FastAPI application
app = FastAPI(
    title="Core Service",
    description="Consolidated service containing orchestrator, primary, checkpoint, and checklist services",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the sub-applications
app.mount("/orchestrator", orchestrator_app)
app.mount("/primary", primary_app) 
app.mount("/checkpoint", checkpoint_app)
app.mount("/checklist", checklist_app)

# Root health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for the core service"""
    return {
        "status": "ok", 
        "service": "core",
        "services": {
            "orchestrator": "mounted at /orchestrator",
            "primary": "mounted at /primary",
            "checkpoint": "mounted at /checkpoint", 
            "checklist": "mounted at /checklist"
        }
    }

@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "message": "Core Service API",
        "services": {
            "orchestrator": {
                "path": "/orchestrator",
                "endpoints": ["/orchestrator/orchestrate", "/orchestrator/health"]
            },
            "primary": {
                "path": "/primary", 
                "endpoints": ["/primary/process", "/primary/health"]
            },
            "checkpoint": {
                "path": "/checkpoint",
                "endpoints": ["/checkpoint/generate", "/checkpoint/health"]
            },
            "checklist": {
                "path": "/checklist",
                "endpoints": ["/checklist/process", "/checklist/debug", "/checklist/health"]
            }
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002,  # Using the orchestrator's original port
        log_level="info"
    )