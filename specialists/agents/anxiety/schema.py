"""
Schema definitions for Anxiety Support Agent
Supports anxiety tracking, coping strategies, and panic attack management
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Literal
from datetime import datetime, date
from enum import Enum


class AnxietyLevel(int, Enum):
    """Anxiety intensity levels"""
    NONE = 0
    MILD = 1
    MODERATE = 2
    SEVERE = 3
    PANIC = 4


class CheckpointState(str, Enum):
    """Conversation flow checkpoints/states"""
    GREETING = "GREETING"
    ASKED_ANXIETY_RATING = "ASKED_ANXIETY_RATING"
    ASK_TRIGGERS = "ASK_TRIGGERS"
    OFFER_COPING_TECHNIQUE = "OFFER_COPING_TECHNIQUE"
    BREATHING_SESSION_RUNNING = "BREATHING_SESSION_RUNNING"
    GROUNDING_EXERCISE = "GROUNDING_EXERCISE"
    LOGGING_ENTRY = "LOGGING_ENTRY"
    ANXIETY_SUMMARY = "ANXIETY_SUMMARY"
    CLOSING = "CLOSING"
    PANIC_ESCALATION = "PANIC_ESCALATION"


class SourceType(str, Enum):
    """Source of the anxiety check-in"""
    CHAT = "chat"
    CALL = "call"
    SCHEDULED = "scheduled"
    PANIC_BUTTON = "panic_button"


class ConsentSettings(BaseModel):
    """User consent settings"""
    voice_analysis: bool = False
    data_use: bool = True


class AnxietyPreferences(BaseModel):
    """User anxiety management preferences"""
    preferred_techniques: List[str] = Field(default_factory=lambda: ["breathing", "grounding"])
    trigger_alerts: bool = True
    panic_button_enabled: bool = True


class UserProfile(BaseModel):
    """User profile data"""
    userId: str
    name: str
    locale: str = "en-US"
    timezone: str = "America/New_York"
    consent: ConsentSettings = Field(default_factory=ConsentSettings)
    anxietyPreferences: AnxietyPreferences = Field(default_factory=AnxietyPreferences)


class AnxietyEntry(BaseModel):
    """Anxiety check-in entry"""
    user_profile_id: str
    conversation_id: str
    timestampISO: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    anxietyScore: int = Field(..., ge=1, le=10)
    triggers: List[str] = Field(default_factory=list)
    physical_symptoms: List[str] = Field(default_factory=list)
    anxiety_level: int = AnxietyLevel.MILD
    notes: Optional[str] = None
    source: str = SourceType.CHAT
    coping_technique_used: Optional[str] = None


class WeeklySummary(BaseModel):
    """Weekly anxiety summary"""
    avgAnxiety: float
    trend: Literal["improving", "worsening", "stable"]
    commonTriggers: List[str] = Field(default_factory=list)
    effectiveTechniques: List[str] = Field(default_factory=list)
    panicEpisodes: int = 0
    week_start: str  # ISO date string
    week_end: str  # ISO date string
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class CopingTechnique(BaseModel):
    """Anxiety coping technique"""
    id: str
    name: str
    description: str
    duration_minutes: int
    anxiety_level_range: List[int]  # e.g., [1, 3] for mild to moderate anxiety
    instructions: List[str]
    tags: List[str]


class AnxietyPromptMapping(BaseModel):
    """Mapping of anxiety scores to appropriate prompts"""
    anxiety_range: List[int]
    prompts: List[str]
    follow_up_questions: List[str]
    suggested_techniques: List[str]


class AnxietyAgentInstance(BaseModel):
    """Main document structure for a user's anxiety agent instance"""
    user_profile_id: str
    agent_instance_id: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    
    # Arrays that will be appended to
    daily_check_ins: List[Dict[str, Any]] = Field(default_factory=list)
    anxiety_tracking: List[Dict[str, Any]] = Field(default_factory=list)
    trigger_patterns: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Static arrays (rarely changed)
    coping_techniques: List[Dict[str, Any]] = Field(default_factory=list)
    anxiety_prompt_mappings: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Current state
    last_check_in: Optional[str] = None  # ISO timestamp
    last_checkpoint: str = "GREETING"
    current_anxiety_level: int = AnxietyLevel.MILD
    total_check_ins: int = 0


class AnxietyRequest(BaseModel):
    """Input request schema for the anxiety agent"""
    user_query: str
    conversation_id: str
    checkpoint: Optional[str] = None
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)
    individual_id: Optional[str] = None
    user_profile_id: str
    agent_instance_id: str


class ToolCall(BaseModel):
    """Tool call structure"""
    name: str
    input: Dict[str, Any]


class AnxietyResponse(BaseModel):
    """Output response schema for the anxiety agent"""
    reply: str
    tool_call: Optional[ToolCall] = None
    conversation_id: str
    checkpoint: str
    context: Dict[str, Any] = Field(default_factory=dict)
    individual_id: Optional[str] = None
    user_profile_id: str
    agent_instance_id: str


class AnxietyAgentLog(BaseModel):
    """Lightweight log entry stored in the `anxiety_agent` collection"""
    user_profile_id: str
    agent_instance_id: str
    conversation_id: str
    text: str
    checkpoint: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    anxietyLevel: int = AnxietyLevel.MILD
    timestampISO: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
