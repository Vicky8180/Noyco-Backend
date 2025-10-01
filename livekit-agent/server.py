"""
HTTP Server wrapper for LiveKit Agent
Provides health check endpoint for Cloud Run while running the agent in background
LiveKit plugins are imported on main thread to avoid registration errors
"""
import asyncio
import logging
import os
import multiprocessing
import sys
import signal
from aiohttp import web
from config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

# Global flag to track agent status
agent_process = None
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
        global agent_started, agent_process
        agent_alive = agent_process is not None and agent_process.is_alive() if agent_process else False
        return web.json_response({
            'status': 'healthy',
            'service': 'livekit-agent',
            'agent_started': agent_started,
            'agent_running': agent_alive
        })
    
    def start_agent_process(self):
        """Start the LiveKit agent in a separate process"""
        global agent_process, agent_started
        
        def run_agent():
            """Run in separate process - has its own main thread for plugin registration"""
            try:
                logger.info("🚀 Starting LiveKit agent in separate process...")
                
                # Import in the new process (this process has its own main thread)
                from livekit.agents import WorkerOptions, cli
                from main import entrypoint
                
                # Run the agent using cli.run_app
                worker_options = WorkerOptions(entrypoint_fnc=entrypoint)
                cli.run_app(worker_options)
                
            except Exception as e:
                logger.error(f"❌ Agent error: {e}", exc_info=True)
                sys.exit(1)
        
        # Start agent in separate process (has its own main thread)
        agent_process = multiprocessing.Process(target=run_agent, daemon=True)
        agent_process.start()
        agent_started = True
        logger.info(f"✅ LiveKit agent process started (PID: {agent_process.pid})")
    
    async def run(self):
        """Run both the HTTP server and LiveKit agent"""
        port = int(os.getenv('PORT', 8080))
        
        # Start the LiveKit agent in background process
        self.start_agent_process()
        
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
            logger.info(f"📡 Received signal {signum}, shutting down...")
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
        finally:
            # Cleanup
            global agent_process
            if agent_process and agent_process.is_alive():
                logger.info("🛑 Terminating agent process...")
                agent_process.terminate()
                agent_process.join(timeout=5)
                if agent_process.is_alive():
                    logger.warning("⚠️  Agent process did not terminate, killing...")
                    agent_process.kill()
            
            await runner.cleanup()
            logger.info("👋 Shutdown complete")


async def main():
    """Main entry point"""
    server = AgentServer()
    await server.run()


if __name__ == "__main__":
    # Required for multiprocessing on some platforms
    multiprocessing.set_start_method('spawn', force=True)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Interrupted by user")
        sys.exit(0)
