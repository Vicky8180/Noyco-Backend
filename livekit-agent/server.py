"""
HTTP Server wrapper for LiveKit Agent
Provides health check endpoint for Cloud Run while running the agent in background
Runs the agent directly in the same process using threading
"""
import asyncio
import logging
import os
import sys
import signal
import threading
import time
from aiohttp import web
from config import get_settings

# Import the agent entrypoint
from main import entrypoint as agent_entrypoint
from livekit.agents import WorkerOptions, cli

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

# Global flag to track agent status
agent_thread = None
agent_started = False
agent_running = False
shutdown_requested = False


class AgentServer:
    def __init__(self):
        self.app = web.Application()
        self.setup_routes()
        
    def setup_routes(self):
        """Setup HTTP routes for health checks"""
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/', self.health_check)
    
    async def health_check(self, request):
        """Health check endpoint for Cloud Run"""
        global agent_started, agent_running, agent_thread, shutdown_requested
        thread_alive = agent_thread.is_alive() if agent_thread else False
        
        return web.json_response({
            'status': 'healthy' if not shutdown_requested else 'shutting_down',
            'service': 'livekit-agent',
            'agent_started': agent_started,
            'agent_running': agent_running and thread_alive,
            'shutdown_requested': shutdown_requested
        })
    
    def start_agent_thread(self):
        """Start the LiveKit agent in a separate thread"""
        global agent_thread, agent_started, agent_running, shutdown_requested
        
        def run_agent():
            """Run the LiveKit agent in a thread"""
            global agent_running, shutdown_requested
            try:
                agent_running = True
                logger.info("🚀 Starting LiveKit agent worker...")
                # Run the LiveKit agent using cli.run_app
                cli.run_app(WorkerOptions(entrypoint_fnc=agent_entrypoint))
            except KeyboardInterrupt:
                logger.info("⚠️ Agent received keyboard interrupt")
            except Exception as e:
                if not shutdown_requested:
                    logger.error(f"❌ Agent error: {e}", exc_info=True)
                else:
                    logger.info(f"⚠️ Agent stopped during shutdown: {e}")
            finally:
                agent_running = False
                logger.info("🛑 Agent thread stopped")
        
        try:
            agent_thread = threading.Thread(target=run_agent, daemon=False, name="LiveKitAgentThread")
            agent_thread.start()
            agent_started = True
            logger.info("✅ LiveKit agent thread started")
        except Exception as e:
            logger.error(f"❌ Failed to start agent thread: {e}")
            agent_started = False
    
    async def run(self):
        """Run both the HTTP server and LiveKit agent"""
        global shutdown_requested
        port = int(os.getenv('PORT', 8080))
        
        # Start the LiveKit agent in background thread
        self.start_agent_thread()
        
        # Give the agent a moment to initialize
        await asyncio.sleep(2)
        
        # Start the HTTP server for health checks
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        
        logger.info(f"✅ HTTP server starting on port {port}")
        await site.start()
        logger.info(f"✅ HTTP server listening on 0.0.0.0:{port} - Ready for Cloud Run health checks")
        
        # Handle graceful shutdown
        shutdown_event = asyncio.Event()
        
        def signal_handler(signum):
            global shutdown_requested
            logger.info(f"📡 Received signal {signum}, initiating graceful shutdown...")
            shutdown_requested = True
            shutdown_event.set()
        
        # Register signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
        
        # Keep server running until shutdown signal
        try:
            await shutdown_event.wait()
        except asyncio.CancelledError:
            logger.info("🛑 Server cancelled, shutting down...")
            shutdown_requested = True
        finally:
            # Cleanup
            global agent_thread, agent_running
            
            logger.info("🧹 Starting server cleanup...")
            
            # Mark as shutting down
            agent_running = False
            
            # Wait for agent thread to finish gracefully (with timeout)
            if agent_thread and agent_thread.is_alive():
                logger.info("⏳ Waiting for agent thread to finish (max 10 seconds)...")
                agent_thread.join(timeout=10.0)
                
                if agent_thread.is_alive():
                    logger.warning("⚠️ Agent thread did not finish in time, proceeding with shutdown")
                else:
                    logger.info("✅ Agent thread finished cleanly")
            
            # Cleanup HTTP server
            await runner.cleanup()
            logger.info("✅ Server cleanup complete")
            logger.info("👋 Shutdown complete")


async def main():
    """Main entry point"""
    server = AgentServer()
    await server.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Interrupted by user")
        sys.exit(0)
