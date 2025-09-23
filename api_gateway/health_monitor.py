# api_gateway/health_monitor.py
"""
Health monitoring system for microservices
Separated from main.py for better organization
"""

import httpx
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any


class HealthMonitor:
    def __init__(self, settings):
        self.settings = settings
        
    async def comprehensive_health_check(self) -> Dict[str, Any]:
        """Comprehensive health check for all microservices in the healthcare platform"""
        # Define all microservices and their health endpoints
        services = {
            "orchestrator": f"{self.settings.ORCHESTRATOR_URL}/health",
            "memory": f"{self.settings.MEMORY_URL}/health", 
            "checkpoint": f"{self.settings.CHECKPOINT_URL}/health",
            "primary_agent": "http://localhost:8002/primary/health",
            "checklist_agent": "http://localhost:8002/checklist/health", 
            "loneliness_agent": "http://localhost:8015/loneliness/health",
            "accountability_agent": "http://localhost:8015/accountability/health",
            "therapy_agent": "http://localhost:8015/therapy/health"
        }
        
        # Filter out None values
        services = {k: v for k, v in services.items() if v is not None}
        
        health_results = {
            "api_gateway": {
                "status": "healthy",
                "response_time": 0,
                "details": "API Gateway is running",
                "version": "1.0.0",
                "timestamp": datetime.now().isoformat()
            }
        }
        
        # Database connections status
        database_status = await self._check_databases()
        
        # Check each microservice
        tasks = [self._check_service_health(name, url) for name, url in services.items()]
        service_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results
        for i, service_name in enumerate(services.keys()):
            result = service_results[i]
            if isinstance(result, Exception):
                health_results[service_name] = {
                    "status": "unhealthy",
                    "error": str(result),
                    "timestamp": datetime.now().isoformat()
                }
            else:
                health_results[service_name] = result
        
        # Calculate overall system health
        healthy_services = sum(1 for service in health_results.values() if service.get("status") == "healthy")
        total_services = len(health_results)
        healthy_databases = sum(1 for db in database_status.values() if db.get("status") == "healthy")
        total_databases = len(database_status)
        
        overall_health = "healthy" if (healthy_services == total_services and healthy_databases == total_databases) else "degraded"
        if healthy_services < total_services * 0.5:  # Less than 50% services healthy
            overall_health = "unhealthy"
        
        # Service categories for better organization
        service_categories = {
            "core_services": ["orchestrator", "memory", "checkpoint", "detector"],
            "agent_services": ["primary_agent", "checklist_agent", "specialized_agents"],
            "specialized_agents": ["nutrition_agent", "human_intervention_agent", "followup_agent", 
                                  "history_agent", "privacy_agent", "medication_agent"],
            "companion_services": ["loneliness_agent", "accountability_agent", "therapy_agent"]
        }
        
        return {
            "overall_status": overall_health,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_services": total_services,
                "healthy_services": healthy_services,
                "unhealthy_services": total_services - healthy_services,
                "health_percentage": round((healthy_services / total_services) * 100, 1) if total_services > 0 else 0
            },
            "platform_info": {
                "name": "Healthcare Platform API Gateway",
                "version": "1.0.0",
                "environment": self.settings.ENVIRONMENT,
                "features": ["authentication", "routing", "billing", "real-time_calls", "socket_io", "fhir_data_conversion", "mediscan_ocr"],
                "api_gateway_url": f"http://{self.settings.SERVICE_HOST}:{self.settings.SERVICE_PORT}"
            },
            "databases": database_status,
            "services": health_results,
            "service_categories": service_categories,
            "endpoints": {
                "health_simple": "/health",
                "health_detailed": "/health/services",
                "api_documentation": "/docs",
                "root_info": "/"
            }
        }

    async def _check_databases(self) -> Dict[str, Dict[str, Any]]:
        """Check database connections"""
        database_status = {}
        
        # Check MongoDB connection
        try:
            import pymongo
            from pymongo import MongoClient
            mongo_client = MongoClient(self.settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
            mongo_client.admin.command('ping')
            database_status["mongodb"] = {
                "status": "healthy",
                "database_name": self.settings.DATABASE_NAME,
                "connection": "active"
            }
            mongo_client.close()
        except ImportError:
            database_status["mongodb"] = {
                "status": "unhealthy",
                "error": "PyMongo package not available",
                "connection": "failed"
            }
        except Exception as e:
            database_status["mongodb"] = {
                "status": "unhealthy",
                "error": str(e),
                "connection": "failed"
            }
        
        # Check Redis connection
        try:
            from redis.asyncio import Redis
            from redis.exceptions import RedisError
            from urllib.parse import urlparse
            
            parsed = urlparse(self.settings.REDIS_URL)
            redis_client = Redis(
                host=parsed.hostname or '127.0.0.1',
                port=parsed.port or 6379,
                db=0,
                socket_connect_timeout=1,
                socket_timeout=2
            )
            await asyncio.wait_for(redis_client.ping(), timeout=5.0)
            database_status["redis"] = {
                "status": "healthy",
                "connection": "active"
            }
            await redis_client.close()
        except ImportError:
            database_status["redis"] = {
                "status": "unhealthy", 
                "error": "Redis package not available",
                "connection": "failed"
            }
        except Exception as e:
            database_status["redis"] = {
                "status": "unhealthy", 
                "error": str(e),
                "connection": "failed"
            }
            
        return database_status

    async def _check_service_health(self, service_name: str, health_url: str) -> Dict[str, Any]:
        """Check individual service health"""
        try:
            start_time = datetime.now()
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                response = await client.get(health_url)
                end_time = datetime.now()
                response_time = (end_time - start_time).total_seconds() * 1000
                
                if response.status_code == 200:
                    response_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                    return {
                        "status": "healthy",
                        "response_time": round(response_time, 2),
                        "status_code": response.status_code,
                        "details": response_data,
                        "url": health_url,
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "response_time": round(response_time, 2),
                        "status_code": response.status_code,
                        "error": f"HTTP {response.status_code}",
                        "url": health_url,
                        "timestamp": datetime.now().isoformat()
                    }
        except httpx.TimeoutException:
            return {
                "status": "unhealthy",
                "error": "Service timeout (>5s)",
                "url": health_url,
                "timestamp": datetime.now().isoformat()
            }
        except httpx.ConnectError:
            return {
                "status": "unhealthy",
                "error": "Connection refused - service may be down",
                "url": health_url,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "url": health_url,
                "timestamp": datetime.now().isoformat()
            }
            
    async def startup_health_display(self):
        """Display health status during startup"""
        print("🚀 " + "="*70)
        print("🚀 Healthcare Platform API Gateway Starting Up")
        print("🚀 " + "="*70)
        
        # Define all microservices and their health endpoints (excluding self during startup)
        services = {
            "Orchestrator": f"{self.settings.ORCHESTRATOR_URL}/health",
            "Memory Service": f"{self.settings.MEMORY_URL}/health", 
            "Checkpoint Service": f"{self.settings.CHECKPOINT_URL}/health",
            "Primary Agent": "http://localhost:8002/primary/health",
            "Checklist Agent": "http://localhost:8002/checklist/health", 
            "Specialized Agents": "http://localhost:8015/health",
            "Loneliness Companion": "http://localhost:8015/loneliness/health",
            "Accountability Agent": "http://localhost:8015/accountability/health",
            "Therapy Agent": "http://localhost:8015/therapy/health"
        }
        
        print("📊 Checking microservices health status...")
        print("-" * 70)
        
        # Check all services concurrently
        tasks = [self._check_service_status(name, url) for name, url in services.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Print results
        healthy_count = 0
        for result in results:
            if isinstance(result, str):
                print(result)
                if "✅" in result:
                    healthy_count += 1
            else:
                print(f"❓ Service check failed: {result}")
        
        print("-" * 70)
        print(f"📈 Health Summary: {healthy_count}/{len(services)} external services healthy")
        print(f"✅ API Gateway            - READY (Port: {self.settings.SERVICE_PORT})")
        
        # Database status
        await self._display_database_status()
        
        # Display available endpoints and features
        self._display_endpoints_and_features()

    async def _check_service_status(self, service_name: str, health_url: str) -> str:
        """Check service status for startup display"""
        try:
            # Use longer timeout for Memory Service
            timeout = 10.0 if "Memory" in service_name else 3.0
            
            # Temporarily suppress httpx logs
            httpx_logger = logging.getLogger("httpx")
            original_level = httpx_logger.level
            httpx_logger.setLevel(logging.WARNING)
            
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
                    response = await client.get(health_url)
                if response.status_code == 200:
                    return f"✅ {service_name:<25} - HEALTHY (Port: {health_url.split(':')[-1].split('/')[0]})"
                else:
                    return f"⚠️  {service_name:<25} - UNHEALTHY (HTTP {response.status_code})"
            finally:
                # Restore original log level
                httpx_logger.setLevel(original_level)
                
        except httpx.ConnectError:
            return f"❌ {service_name:<25} - OFFLINE (Connection refused)"
        except httpx.TimeoutException:
            timeout_msg = ">10s" if "Memory" in service_name else ">3s"
            return f"⏰ {service_name:<25} - TIMEOUT ({timeout_msg})"
        except Exception as e:
            return f"❓ {service_name:<25} - ERROR ({str(e)[:30]}...)"

    async def _display_database_status(self):
        """Display database connection status"""
        print("\n🗃️  Database Connections:")
        print("-" * 70)
        
        # Check MongoDB
        try:
            import pymongo
            from pymongo import MongoClient
            mongo_client = MongoClient(self.settings.MONGODB_URI, serverSelectionTimeoutMS=3000)
            mongo_client.admin.command('ping')
            print(f"✅ MongoDB               - CONNECTED ({self.settings.DATABASE_NAME})")
            mongo_client.close()
        except ImportError as e:
            print(f"❌ MongoDB               - IMPORT FAILED ({str(e)[:30]}...)")
        except Exception as e:
            print(f"❌ MongoDB               - FAILED ({str(e)[:30]}...)")
        
        # Check Redis
        try:
            from redis.asyncio import Redis
            from urllib.parse import urlparse
            parsed = urlparse(self.settings.REDIS_URL)
            redis_client = Redis(
                host=parsed.hostname or '127.0.0.1',
                port=parsed.port or 6379,
                db=0,
                socket_connect_timeout=1,
                socket_timeout=2
            )
            await asyncio.wait_for(redis_client.ping(), timeout=3.0)
            print(f"✅ Redis                 - CONNECTED ({parsed.hostname}:{parsed.port})")
            await redis_client.close()
        except Exception as e:
            print(f"❌ Redis                 - FAILED ({str(e)[:30]}...)")

    def _display_endpoints_and_features(self):
        """Display available endpoints and platform features"""
        print("-" * 70)
        print("🔗 Available Endpoints:")
        print(f"   • Health Check (Simple): http://{self.settings.SERVICE_HOST}:{self.settings.SERVICE_PORT}/health")
        print(f"   • Health Check (Detailed): http://{self.settings.SERVICE_HOST}:{self.settings.SERVICE_PORT}/health/services")
        print(f"   • API Documentation: http://{self.settings.SERVICE_HOST}:{self.settings.SERVICE_PORT}/docs")
        print(f"   • LiveKit Voice: http://{self.settings.SERVICE_HOST}:{self.settings.SERVICE_PORT}/api/v1/voice/*")
        print(f"   • Socket.IO: ws://{self.settings.SERVICE_HOST}:{self.settings.SERVICE_PORT}/socket.io/")
        
        print("\n🎯 Platform Features:")
        print("   • Authentication & JWT")
        print("   • Real-time calls & Socket.IO") 
        print("   • FHIR data conversion")
        print("   • Medical scan OCR")
        print("   • Billing & Stripe integration")
        print("   • Voice assistance (LiveKit)")
        print("   • Multi-agent conversation system")
        
        print("\n" + "="*70)
        print("🚀 API Gateway Ready - Healthcare Platform Operational!")
        print("="*70 + "\n")
