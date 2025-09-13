from datetime import datetime
from typing import Dict, Set, Any, Optional
import asyncio

from .handlers.call_handlers import CallHandlers
from .handlers.patient_handlers import PatientHandlers

class SocketEventHandlers:
    """Main Socket.IO event handler class that manages all socket events"""

    def __init__(self, sio):
        self.sio = sio
        self.active_calls: Dict[str, Dict] = {}
        self.connected_clients: Set[str] = set()

        # Initialize specialized handlers
        self.call_handlers = CallHandlers(sio, self.active_calls)
        self.patient_handlers = PatientHandlers(sio)

        # Register all event handlers
        self._register_events()

    def _register_events(self):
        """Register all socket event handlers with the Socket.IO instance"""
        # Connection events
        @self.sio.event
        async def connect(sid, environ):
            await self.handle_connect(sid, environ)

        @self.sio.event
        async def disconnect(sid):
            await self.handle_disconnect(sid)

        # Call-related events
        @self.sio.event
        async def answer_call(sid, data):
            await self.call_handlers.handle_answer_call(sid, data)

        @self.sio.event
        async def reject_call(sid, data):
            await self.call_handlers.handle_reject_call(sid, data)

        @self.sio.event
        async def end_call(sid, data):
            await self.call_handlers.handle_end_call(sid, data)

        @self.sio.event
        async def toggle_mute(sid, data):
            await self.call_handlers.handle_toggle_mute(sid, data)

        @self.sio.event
        async def send_message(sid, data):
            await self.call_handlers.handle_send_message(sid, data)

        @self.sio.event
        async def add_note(sid, data):
            await self.call_handlers.handle_add_note(sid, data)

        # Patient-specific events
        @self.sio.event
        async def join_patient_room(sid, data):
            await self.patient_handlers.handle_join_patient_room(sid, data)

        @self.sio.event
        async def leave_patient_room(sid, data):
            await self.patient_handlers.handle_leave_patient_room(sid, data)

        @self.sio.event
        async def broadcast_patient_update(sid, data):
            await self.patient_handlers.handle_broadcast_patient_update(sid, data)

    async def handle_connect(self, sid, environ):
        """Handle client connection"""
        self.connected_clients.add(sid)
        print(f"Client {sid} connected")
        await self.sio.emit('connection_status', {'status': 'connected', 'sid': sid}, room=sid)

    async def handle_disconnect(self, sid):
        """Handle client disconnection"""
        self.connected_clients.discard(sid)
        # Remove from active calls if exists
        self.call_handlers.cleanup_user_calls(sid)
        print(f"Client {sid} disconnected")

    async def trigger_incoming_call(self, call_data):
        """Emit an incoming call event to clients - called from REST API"""
        await self.sio.emit('incoming_call', call_data)

    def get_active_calls(self):
        """Return active calls data - called from REST API"""
        return {
            "success": True,
            "activeCalls": self.active_calls,
            "connectedClients": len(self.connected_clients)
        }
