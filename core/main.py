"""
Core Service Main Application
Consolidates orchestrator, primary, checkpoint, and checklist services into a single application
with sub-mounted applications accessible via different paths.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import get_core_config

# Get the config instance
config = get_core_config()

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

@app.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check that verifies all mounted microservices"""
    import httpx
    import asyncio
    from datetime import datetime
    
    base_url = f"http://localhost:{config.port}"
    
    services = {
        "orchestrator": f"{base_url}/orchestrator/health",
        "primary": f"{base_url}/primary/health", 
        "checkpoint": f"{base_url}/checkpoint/health",
        "checklist": f"{base_url}/checklist/health"
    }
    
    async def check_service(name: str, url: str):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "name": name,
                        "status": "healthy",
                        "response": data,
                        "response_time": response.elapsed.total_seconds() * 1000
                    }
                else:
                    return {
                        "name": name,
                        "status": "unhealthy",
                        "error": f"HTTP {response.status_code}",
                        "response_time": response.elapsed.total_seconds() * 1000
                    }
        except Exception as e:
            return {
                "name": name,
                "status": "unhealthy",
                "error": str(e)
            }
    
    # Check all services concurrently
    tasks = [check_service(name, url) for name, url in services.items()]
    results = await asyncio.gather(*tasks)
    
    # Calculate overall health
    healthy_count = sum(1 for result in results if result["status"] == "healthy")
    total_count = len(results)
    overall_status = "healthy" if healthy_count == total_count else "degraded"
    
    return {
        "status": overall_status,
        "service": "core",
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_services": total_count,
            "healthy_services": healthy_count,
            "unhealthy_services": total_count - healthy_count
        },
        "services": {result["name"]: result for result in results}
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
        port=config.SERVICE_PORT,  # Using the orchestrator's original port
        log_level="info"
    )