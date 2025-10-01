"""
HTTP Server wrapper for LiveKit Agent
Provides health check endpoint for Cloud Run while running the agent in background
"""
import asyncio
import logging
import os
import threading
import sys
from aiohttp import web
from config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

# Global flag to track agent status
agent_running = False
agent_started = False

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
        global agent_started, agent_running
        return web.json_response({
            'status': 'healthy',
            'service': 'livekit-agent',
            'agent_started': agent_started,
            'agent_running': agent_running
        })
    
    def start_agent_thread(self):
        """Start the LiveKit agent in a separate thread"""
        global agent_running, agent_started
        
        def run_agent():
            global agent_running, agent_started
            try:
                logger.info("🚀 Starting LiveKit agent in background thread...")
                agent_started = True
                agent_running = True
                
                # Import here to avoid issues with event loop
                from livekit.agents import WorkerOptions, cli
                from main import entrypoint
                
                # Run the agent using cli.run_app
                worker_options = WorkerOptions(entrypoint_fnc=entrypoint)
                cli.run_app(worker_options)
                
            except Exception as e:
                logger.error(f"❌ Agent error: {e}", exc_info=True)
                agent_running = False
        
        # Start agent in daemon thread
        agent_thread = threading.Thread(target=run_agent, daemon=True)
        agent_thread.start()
        logger.info("✅ LiveKit agent thread started")
    
    async def run(self):
        """Run both the HTTP server and LiveKit agent"""
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
        
        # Keep server running
        try:
            while True:
                await asyncio.sleep(3600)  # Sleep for an hour
        except asyncio.CancelledError:
            logger.info("🛑 Server cancelled, shutting down...")
        finally:
            await runner.cleanup()
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
