# """
# HTTP Server wrapper for LiveKit Agent
# Provides health check endpoint for Cloud Run while running the agent in background
# Runs the agent directly in the same process using threading
# """
# import asyncio
# import logging
# import os
# import sys
# import signal
# import threading
# import time
# from aiohttp import web
# from config import get_settings

# # Import the agent entrypoint
# from main import entrypoint as agent_entrypoint
# from livekit.agents import WorkerOptions, cli

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# settings = get_settings()

# # Global flag to track agent status
# agent_thread = None
# agent_started = False
# agent_running = False
# shutdown_requested = False


# class AgentServer:
#     def __init__(self):
#         self.app = web.Application()
#         self.setup_routes()
        
#     def setup_routes(self):
#         """Setup HTTP routes for health checks"""
#         self.app.router.add_get('/health', self.health_check)
#         self.app.router.add_get('/', self.health_check)
    
#     async def health_check(self, request):
#         """Health check endpoint for Cloud Run"""
#         global agent_started, agent_running, agent_thread, shutdown_requested
#         thread_alive = agent_thread.is_alive() if agent_thread else False
        
#         return web.json_response({
#             'status': 'healthy' if not shutdown_requested else 'shutting_down',
#             'service': 'livekit-agent',
#             'agent_started': agent_started,
#             'agent_running': agent_running and thread_alive,
#             'shutdown_requested': shutdown_requested
#         })
    
#     def start_agent_thread(self):
#         """Start the LiveKit agent in a separate thread"""
#         global agent_thread, agent_started, agent_running, shutdown_requested
        
#         def run_agent():
#             """Run the LiveKit agent in a thread"""
#             global agent_running, shutdown_requested
#             try:
#                 agent_running = True
#                 logger.info("🚀 Starting LiveKit agent worker...")
#                 # Run the LiveKit agent using cli.run_app
#                 cli.run_app(WorkerOptions(entrypoint_fnc=agent_entrypoint))
#             except KeyboardInterrupt:
#                 logger.info("⚠️ Agent received keyboard interrupt")
#             except Exception as e:
#                 if not shutdown_requested:
#                     logger.error(f"❌ Agent error: {e}", exc_info=True)
#                 else:
#                     logger.info(f"⚠️ Agent stopped during shutdown: {e}")
#             finally:
#                 agent_running = False
#                 logger.info("🛑 Agent thread stopped")
        
#         try:
#             agent_thread = threading.Thread(target=run_agent, daemon=False, name="LiveKitAgentThread")
#             agent_thread.start()
#             agent_started = True
#             logger.info("✅ LiveKit agent thread started")
#         except Exception as e:
#             logger.error(f"❌ Failed to start agent thread: {e}")
#             agent_started = False
    
#     async def run(self):
#         """Run both the HTTP server and LiveKit agent"""
#         global shutdown_requested
#         port = int(os.getenv('PORT', 8080))
        
#         # Start the LiveKit agent in background thread
#         self.start_agent_thread()
        
#         # Give the agent a moment to initialize
#         await asyncio.sleep(2)
        
#         # Start the HTTP server for health checks
#         runner = web.AppRunner(self.app)
#         await runner.setup()
#         site = web.TCPSite(runner, '0.0.0.0', port)
        
#         logger.info(f"✅ HTTP server starting on port {port}")
#         await site.start()
#         logger.info(f"✅ HTTP server listening on 0.0.0.0:{port} - Ready for Cloud Run health checks")
        
#         # Handle graceful shutdown
#         shutdown_event = asyncio.Event()
        
#         def signal_handler(signum):
#             global shutdown_requested
#             logger.info(f"📡 Received signal {signum}, initiating graceful shutdown...")
#             shutdown_requested = True
#             shutdown_event.set()
        
#         # Register signal handlers
#         loop = asyncio.get_event_loop()
#         for sig in (signal.SIGTERM, signal.SIGINT):
#             loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
        
#         # Keep server running until shutdown signal
#         try:
#             await shutdown_event.wait()
#         except asyncio.CancelledError:
#             logger.info("🛑 Server cancelled, shutting down...")
#             shutdown_requested = True
#         finally:
#             # Cleanup
#             global agent_thread, agent_running
            
#             logger.info("🧹 Starting server cleanup...")
            
#             # Mark as shutting down
#             agent_running = False
            
#             # Wait for agent thread to finish gracefully (with timeout)
#             if agent_thread and agent_thread.is_alive():
#                 logger.info("⏳ Waiting for agent thread to finish (max 10 seconds)...")
#                 agent_thread.join(timeout=10.0)
                
#                 if agent_thread.is_alive():
#                     logger.warning("⚠️ Agent thread did not finish in time, proceeding with shutdown")
#                 else:
#                     logger.info("✅ Agent thread finished cleanly")
            
#             # Cleanup HTTP server
#             await runner.cleanup()
#             logger.info("✅ Server cleanup complete")
#             logger.info("👋 Shutdown complete")


# async def main():
#     """Main entry point"""
#     server = AgentServer()
#     await server.run()


# if __name__ == "__main__":
#     try:
#         asyncio.run(main())
#     except KeyboardInterrupt:
#         logger.info("👋 Interrupted by user")
#         sys.exit(0)


"""
Multi-Tenant HTTP Server for LiveKit Agent
Runs a FastAPI server with health checks and session management
The agent worker runs in the same process handling multiple concurrent sessions
"""
import asyncio
import logging
import os
import sys
import signal
from typing import Dict
from aiohttp import web
from datetime import datetime

from config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

# Import after logging is configured
from main import entrypoint, session_manager, cleanup_worker
from livekit.agents import WorkerOptions, cli

# Global state
agent_worker_task = None
cleanup_task = None
shutdown_requested = False


class MultiTenantAgentServer:
    """
    HTTP server for multi-tenant LiveKit agent
    Provides health checks and metrics
    """
    
    def __init__(self):
        self.app = web.Application()
        self.setup_routes()
        self.start_time = datetime.utcnow()
        
    def setup_routes(self):
        """Setup HTTP routes"""
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/', self.root)
        self.app.router.add_get('/sessions', self.list_sessions)
        self.app.router.add_get('/metrics', self.get_metrics)
    
    async def health_check(self, request):
        """Health check endpoint for Cloud Run"""
        global agent_worker_task, shutdown_requested
        
        worker_running = agent_worker_task and not agent_worker_task.done()
        
        return web.json_response({
            'status': 'healthy' if not shutdown_requested else 'shutting_down',
            'service': 'livekit-agent-multitenant',
            'worker_running': worker_running,
            'shutdown_requested': shutdown_requested,
            'uptime_seconds': (datetime.utcnow() - self.start_time).total_seconds()
        })
    
    async def root(self, request):
        """Root endpoint"""
        return web.json_response({
            'service': 'Noyco Multi-Tenant LiveKit Agent',
            'version': '2.0.0',
            'mode': 'multi-tenant',
            'endpoints': ['/health', '/sessions', '/metrics']
        })
    
    async def list_sessions(self, request):
        """List all active sessions"""
        try:
            sessions = await session_manager.get_all_sessions()
            
            # Format session info
            session_list = []
            for session_id, session_info in sessions.items():
                session_list.append({
                    'session_id': session_id,
                    'status': session_info.get('status'),
                    'created_at': session_info.get('created_at').isoformat() if session_info.get('created_at') else None,
                    'last_activity': session_info.get('last_activity').isoformat() if session_info.get('last_activity') else None,
                    'user_profile_id': session_info.get('data', {}).get('user_profile_id')
                })
            
            return web.json_response({
                'total_sessions': len(sessions),
                'sessions': session_list
            })
        except Exception as e:
            logger.error(f"Error listing sessions: {e}")
            return web.json_response({
                'error': str(e)
            }, status=500)
    
    async def get_metrics(self, request):
        """Get service metrics"""
        try:
            sessions = await session_manager.get_all_sessions()
            
            return web.json_response({
                'uptime_seconds': (datetime.utcnow() - self.start_time).total_seconds(),
                'total_active_sessions': len(sessions),
                'worker_status': 'running' if agent_worker_task and not agent_worker_task.done() else 'stopped',
                'cleanup_worker_status': 'running' if cleanup_task and not cleanup_task.done() else 'stopped'
            })
        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            return web.json_response({
                'error': str(e)
            }, status=500)
    
    async def start_agent_worker(self):
        """Start the LiveKit agent worker as an async task"""
        global agent_worker_task
        
        try:
            logger.info("🚀 Starting multi-tenant LiveKit agent worker...")
            
            # Create worker options
            worker_opts = WorkerOptions(entrypoint_fnc=entrypoint)
            
            # Run the worker in a separate thread (LiveKit CLI uses blocking calls)
            def run_worker_sync():
                try:
                    cli.run_app(worker_opts)
                except KeyboardInterrupt:
                    logger.info("⚠️ Worker interrupted")
                except Exception as e:
                    if not shutdown_requested:
                        logger.error(f"❌ Worker error: {e}", exc_info=True)
            
            # Run in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            agent_worker_task = loop.run_in_executor(None, run_worker_sync)
            logger.info("✅ Multi-tenant agent worker started")
            
        except Exception as e:
            logger.error(f"❌ Failed to start agent worker: {e}")
            raise
    
    async def start_cleanup_worker(self):
        """Start the cleanup worker"""
        global cleanup_task
        
        try:
            logger.info("🧹 Starting cleanup worker...")
            cleanup_task = asyncio.create_task(cleanup_worker())
            logger.info("✅ Cleanup worker started")
        except Exception as e:
            logger.error(f"❌ Failed to start cleanup worker: {e}")
    
    async def run(self):
        """Run the multi-tenant server"""
        global shutdown_requested
        
        port = int(os.getenv('PORT', 8080))
        
        # Start background workers
        await self.start_agent_worker()
        await self.start_cleanup_worker()
        
        # Give workers a moment to initialize
        await asyncio.sleep(2)
        
        # Start HTTP server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        
        logger.info(f"✅ HTTP server starting on port {port}")
        await site.start()
        logger.info(f"✅ Multi-tenant server listening on 0.0.0.0:{port}")
        logger.info(f"✅ Ready to handle multiple concurrent sessions")
        
        # Graceful shutdown handling
        shutdown_event = asyncio.Event()
        signal_received = False
        
        def signal_handler(signum):
            global shutdown_requested
            nonlocal signal_received
            
            # Prevent multiple signal handling
            if signal_received:
                logger.warning(f"⚠️ Signal {signum} received again, forcing exit...")
                sys.exit(1)
            
            signal_received = True
            logger.info(f"📡 Received signal {signum}, initiating graceful shutdown...")
            shutdown_requested = True
            shutdown_event.set()
        
        # Register signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
        
        # Keep server running until shutdown
        try:
            await shutdown_event.wait()
        except asyncio.CancelledError:
            logger.info("🛑 Server cancelled, shutting down...")
            shutdown_requested = True
        finally:
            # Cleanup
            global agent_worker_task, cleanup_task
            
            logger.info("🧹 Starting server cleanup...")
            
            try:
                # Cancel cleanup worker
                if cleanup_task and not cleanup_task.done():
                    logger.info("⏳ Stopping cleanup worker...")
                    cleanup_task.cancel()
                    try:
                        await asyncio.wait_for(cleanup_task, timeout=2.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                
                # Wait for agent worker to finish (with timeout)
                if agent_worker_task and not agent_worker_task.done():
                    logger.info("⏳ Stopping agent worker (max 5 seconds)...")
                    try:
                        await asyncio.wait_for(agent_worker_task, timeout=5.0)
                    except asyncio.TimeoutError:
                        logger.warning("⚠️ Agent worker did not stop in time, forcing shutdown")
                    except Exception as e:
                        logger.warning(f"⚠️ Error waiting for agent worker: {e}")
                
                # Cleanup HTTP server
                logger.info("⏳ Cleaning up HTTP server...")
                await asyncio.wait_for(runner.cleanup(), timeout=2.0)
                logger.info("✅ Server cleanup complete")
                
            except asyncio.TimeoutError:
                logger.error("❌ Cleanup timed out, forcing exit")
            except Exception as e:
                logger.error(f"❌ Error during cleanup: {e}")
            finally:
                logger.info("👋 Shutdown complete")
                # Force exit to prevent hanging
                sys.exit(0)


async def main():
    """Main entry point"""
    server = MultiTenantAgentServer()
    await server.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Interrupted by user")
        sys.exit(0)
