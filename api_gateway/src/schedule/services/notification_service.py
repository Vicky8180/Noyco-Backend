
# ============================================================================
# services/notification_service.py - Notification Service
# ============================================================================

import asyncio
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications about scheduled calls"""

    def __init__(self):
        self.notification_handlers = {}

    async def register_handler(self, event_type: str, handler_func):
        """Register a notification handler for specific events"""
        if event_type not in self.notification_handlers:
            self.notification_handlers[event_type] = []
        self.notification_handlers[event_type].append(handler_func)

    async def send_notification(self, event_type: str, data: Dict[str, Any]):
        """Send notification for a specific event"""
        try:
            if event_type in self.notification_handlers:
                for handler in self.notification_handlers[event_type]:
                    await handler(data)

        except Exception as e:
            logger.error(f"Error sending notification for {event_type}: {e}")

    async def notify_call_scheduled(self, schedule_data: Dict[str, Any]):
        """Notify when a call is scheduled"""
        await self.send_notification("call_scheduled", schedule_data)

    async def notify_call_starting(self, schedule_data: Dict[str, Any]):
        """Notify when a call is about to start"""
        await self.send_notification("call_starting", schedule_data)

    async def notify_call_completed(self, call_data: Dict[str, Any]):
        """Notify when a call is completed"""
        await self.send_notification("call_completed", call_data)

    async def notify_call_failed(self, call_data: Dict[str, Any]):
        """Notify when a call fails"""
        await self.send_notification("call_failed", call_data)

    async def notify_call_cancelled(self, call_data: Dict[str, Any]):
        """Notify when a call is cancelled"""
        await self.send_notification("call_cancelled", call_data)

