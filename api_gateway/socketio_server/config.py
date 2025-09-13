import socketio
from .events import SocketEventHandlers
from api_gateway.config import get_settings

def create_socketio_server(allowed_origins=None):
    """Create and configure the Socket.IO server"""
    if allowed_origins is None:
        settings = get_settings()
        allowed_origins = settings.SOCKETIO_CORS_ORIGINS.split(",")

    # Create Socket.IO server with proper CORS configuration
    sio = socketio.AsyncServer(
        async_mode='asgi',
        cors_allowed_origins=allowed_origins,
        logger=get_settings().SOCKETIO_LOGGER,
        engineio_logger=get_settings().SOCKETIO_ENGINEIO_LOGGER
    )

    # Initialize event handlers
    event_handlers = SocketEventHandlers(sio)

    return sio, event_handlers
