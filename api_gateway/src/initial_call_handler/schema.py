# =======================
# schema.py
# =======================

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from enum import Enum

class AgentType(str, Enum):
    EMOTIONAL_COMPANION = "emotional"
    ACCOUNTABILITY_BUDDY = "accountability" 
    VOICE_COMPANION = "loneliness"
    THERAPY_CHECKIN = "mental_therapy"
    SOCIAL_ANXIETY_PREP = "social_anxiety"
    
    def get_agent_name(self) -> str:
        """Get the human-readable name of the agent"""
        agent_names = {
            "emotional": "Emotional Companion Agent",
            "accountability": "Accountability Buddy",
            "loneliness": "Chronically Lonely People Agent",
            "mental_therapy": "Mental Health Check-In",
            "social_anxiety": "Pre-Social Anxiety Prep Agent"
        }
        return agent_names.get(self.value, self.value)

class ConversationMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    conversation_history: List[ConversationMessage] = []
    user_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    detected_intent: Optional[str] = None
    confidence: Optional[float] = None
    selected_agent: Optional[AgentType] = None
    selected_agent_name: Optional[str] = None
    should_route: bool = False
    conversation_turn: int
    needs_more_conversation: bool = False

class IntentResult(BaseModel):
    intent: str
    confidence: float
    reasoning: str
    keywords: List[str]

class AgentSelection(BaseModel):
    selected_agent: AgentType
    agent_name: str
    confidence: float
    reasoning: str
    should_route: bool = False
    needs_more_conversation: bool = False
