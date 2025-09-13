from datetime import datetime
from typing import Dict, Any

class CallHandlers:
    """Handlers for call-related socket events"""

    def __init__(self, sio, active_calls=None):
        self.sio = sio
        self.active_calls = active_calls or {}

    def cleanup_user_calls(self, sid):
        """Clean up calls when a user disconnects"""
        for call_id, call_info in list(self.active_calls.items()):
            if call_info.get('participants', {}).get(sid):
                del self.active_calls[call_id]['participants'][sid]
                if not self.active_calls[call_id]['participants']:
                    del self.active_calls[call_id]

    async def handle_answer_call(self, sid, data):
        """Handle call answer"""
        call_id = data.get('callId')
        if call_id:
            self.active_calls[call_id] = {
                'status': 'active',
                'startTime': datetime.now().isoformat(),
                'participants': {sid: {'role': 'caller', 'muted': False}},
                'messages': []
            }

            await self.sio.emit('call_answered', {
                'callId': call_id,
                'status': 'active',
                'startTime': self.active_calls[call_id]['startTime']
            }, room=sid)

            print(f"Call {call_id} answered by {sid}")

    async def handle_reject_call(self, sid, data):
        """Handle call rejection"""
        call_id = data.get('callId')
        await self.sio.emit('call_rejected', {'callId': call_id}, room=sid)
        print(f"Call {call_id} rejected by {sid}")

    async def handle_end_call(self, sid, data):
        """Handle call end"""
        call_id = data.get('callId')
        if call_id in self.active_calls:
            end_time = datetime.now().isoformat()
            start_time = datetime.fromisoformat(self.active_calls[call_id]['startTime'])
            duration = (datetime.now() - start_time).total_seconds()

            call_summary = {
                'callId': call_id,
                'duration': duration,
                'endTime': end_time,
                'messages': self.active_calls[call_id]['messages']
            }

            await self.sio.emit('call_ended', call_summary, room=sid)
            del self.active_calls[call_id]
            print(f"Call {call_id} ended by {sid}")

    async def handle_toggle_mute(self, sid, data):
        """Handle mute toggle"""
        call_id = data.get('callId')
        muted = data.get('muted', False)

        if call_id in self.active_calls and sid in self.active_calls[call_id]['participants']:
            self.active_calls[call_id]['participants'][sid]['muted'] = muted

            await self.sio.emit('mute_toggled', {
                'callId': call_id,
                'muted': muted
            }, room=sid)

    async def handle_send_message(self, sid, data):
        """Handle chat messages during call"""
        call_id = data.get('callId')
        message = data.get('message', '')
        sender = data.get('sender', 'Anonymous')

        if call_id in self.active_calls:
            message_data = {
                'id': f"msg_{datetime.now().timestamp()}",
                'sender': sender,
                'message': message,
                'timestamp': datetime.now().isoformat(),
                'type': 'chat'
            }

            self.active_calls[call_id]['messages'].append(message_data)

            # Broadcast to all participants in the call
            for participant_sid in self.active_calls[call_id]['participants']:
                await self.sio.emit('new_message', message_data, room=participant_sid)

    async def handle_add_note(self, sid, data):
        """Handle adding notes during call"""
        call_id = data.get('callId')
        note = data.get('note', '')

        if call_id in self.active_calls:
            note_data = {
                'id': f"note_{datetime.now().timestamp()}",
                'content': note,
                'timestamp': datetime.now().isoformat(),
                'type': 'note'
            }

            self.active_calls[call_id]['messages'].append(note_data)

            await self.sio.emit('note_added', note_data, room=sid)
