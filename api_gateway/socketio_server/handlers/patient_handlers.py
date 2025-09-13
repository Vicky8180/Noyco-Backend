from datetime import datetime

class PatientHandlers:
    """Handlers for patient-related socket events"""

    def __init__(self, sio):
        self.sio = sio

    async def handle_join_patient_room(self, sid, data):
        """Allow healthcare professionals to join patient-specific rooms"""
        patient_id = data.get('patientId')
        user_role = data.get('userRole')

        if patient_id and user_role in ['doctor', 'nurse', 'assistant']:
            room_name = f"patient_{patient_id}"
            await self.sio.enter_room(sid, room_name)
            await self.sio.emit('joined_patient_room', {
                'patientId': patient_id,
                'roomName': room_name
            }, room=sid)

    async def handle_leave_patient_room(self, sid, data):
        """Leave patient-specific room"""
        patient_id = data.get('patientId')
        if patient_id:
            room_name = f"patient_{patient_id}"
            await self.sio.leave_room(sid, room_name)
            await self.sio.emit('left_patient_room', {
                'patientId': patient_id,
                'roomName': room_name
            }, room=sid)

    async def handle_broadcast_patient_update(self, sid, data):
        """Broadcast patient updates to all users in patient room"""
        patient_id = data.get('patientId')
        update_data = data.get('updateData')

        if patient_id and update_data:
            room_name = f"patient_{patient_id}"
            await self.sio.emit('patient_update', {
                'patientId': patient_id,
                'updateData': update_data,
                'timestamp': datetime.now().isoformat()
            }, room=room_name)
