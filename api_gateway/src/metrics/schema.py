from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class MessageSchema(BaseModel):
    role: str
    content: str
    timestamp: Optional[datetime] = None

class ConversationInstanceSchema(BaseModel):
    conversation_id: str
    agent_instance_id: str
    detected_agent: str
    last_message_preview: str
    message_count: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_active: bool

class ConversationGroupSchema(BaseModel):
    agent_instance_id: str
    goal_title: Optional[str] = None  # Add goal title field
    detected_agent: str
    conversation_count: int
    conversations: List[ConversationInstanceSchema]
    last_activity: datetime
    total_messages: int

class ConversationDetailSchema(BaseModel):
    conversation_id: str
    agent_instance_id: str
    detected_agent: str
    context: List[MessageSchema]
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_active: bool
    has_summary: bool
    summary: Optional[str] = None

class ConversationsResponseSchema(BaseModel):
    user_profile_id: str
    agent_type: Optional[str] = None
    conversation_groups: List[ConversationGroupSchema]
    total_conversations: int
    total_messages: int

class AgentTypeSchema(BaseModel):
    agent_type: str
    count: int
    last_activity: Optional[datetime] = None
