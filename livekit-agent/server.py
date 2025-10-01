"""
HTTP Server wrapper for LiveKit Agent
Provides health check endpoint for Cloud Run while running the agent in background
Uses subprocess to run agent in separate process with its own main thread
"""
import asyncio
import logging
import os
import sys
import signal
import subprocess
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
        agent_alive = False
        if agent_process:
            # Check if process is still running
            poll = agent_process.poll()
            agent_alive = poll is None  # None means process is still running
        
        return web.json_response({
            'status': 'healthy',
            'service': 'livekit-agent',
            'agent_started': agent_started,
            'agent_running': agent_alive
        })
    
    def start_agent_process(self):
        """Start the LiveKit agent in a separate process using subprocess"""
        global agent_process, agent_started
        
        # Start agent using subprocess - runs main.py with 'start' command
        # This creates a completely separate process with its own main thread
        try:
            agent_process = subprocess.Popen(
                [sys.executable, '-u', 'main.py', 'start'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            agent_started = True
            logger.info(f"✅ LiveKit agent process started (PID: {agent_process.pid})")
            
            # Start a task to monitor agent output
            asyncio.create_task(self.monitor_agent_output())
            
        except Exception as e:
            logger.error(f"❌ Failed to start agent process: {e}")
            agent_started = False
    
    async def monitor_agent_output(self):
        """Monitor and log agent process output"""
        global agent_process
        if not agent_process or not agent_process.stdout:
            return
        
        try:
            # Read agent output line by line in non-blocking way
            loop = asyncio.get_event_loop()
            while True:
                line = await loop.run_in_executor(None, agent_process.stdout.readline)
                if not line:
                    break
                logger.info(f"[Agent] {line.rstrip()}")
        except Exception as e:
            logger.error(f"Error monitoring agent output: {e}")
    
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
            if agent_process:
                logger.info("🛑 Terminating agent process...")
                try:
                    agent_process.terminate()
                    agent_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("⚠️  Agent process did not terminate, killing...")
                    agent_process.kill()
                    agent_process.wait()
            
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
