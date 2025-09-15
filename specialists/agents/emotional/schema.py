"""
Schema definitions for Emotional Companion Agent
Supports emotional state tracking, comfort sessions, and emotional wellness monitoring
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Literal
from datetime import datetime, date
from enum import Enum


class EmotionalIntensity(int, Enum):
    """Emotional intensity levels for monitoring"""
    VERY_LOW = 1
    LOW = 2
    MILD = 3
    MODERATE = 4
    HIGH = 5
    VERY_HIGH = 6
    SEVERE = 7
    EXTREME = 8


class CheckpointState(str, Enum):
    """Conversation flow checkpoints/states"""
    GREETING = "GREETING"
    EMOTIONAL_CHECK_IN = "EMOTIONAL_CHECK_IN"
    EXPLORING_FEELINGS = "EXPLORING_FEELINGS"
    OFFERING_COMFORT = "OFFERING_COMFORT"
    COMFORT_SESSION_RUNNING = "COMFORT_SESSION_RUNNING"
    VALIDATION_AND_SUPPORT = "VALIDATION_AND_SUPPORT"
    COPING_STRATEGIES = "COPING_STRATEGIES"
    EMOTIONAL_SUMMARY = "EMOTIONAL_SUMMARY"
    CLOSING_WITH_CARE = "CLOSING_WITH_CARE"
    CRISIS_SUPPORT = "CRISIS_SUPPORT"


class SourceType(str, Enum):
    """Source of the emotional check-in"""
    CHAT = "chat"
    CALL = "call"
    SCHEDULED = "scheduled"
    CRISIS = "crisis"


class EmotionalState(str, Enum):
    """Primary emotional states"""
    DISTRESSED = "distressed"
    SEEKING_COMFORT = "seeking_comfort"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    OVERWHELMED = "overwhelmed"
    ANXIOUS = "anxious"
    DEPRESSED = "depressed"
    LONELY = "lonely"
    ANGRY = "angry"
    FEARFUL = "fearful"
    HOPEFUL = "hopeful"
    GRATEFUL = "grateful"


class ComfortPreferences(BaseModel):
    """User comfort preferences"""
    preferred_comfort_types: List[str] = Field(default_factory=lambda: ["listening", "validation", "gentle_guidance"])
    comfort_session_frequency: str = "as_needed"  # daily, weekly, as_needed
    preferred_time_of_day: Optional[str] = None  # morning, afternoon, evening


class UserProfile(BaseModel):
    """User profile data for emotional support"""
    userId: str
    name: str
    locale: str = "en-US"
    timezone: str = "America/New_York"
    comfort_preferences: ComfortPreferences = Field(default_factory=ComfortPreferences)
    emotional_triggers: List[str] = Field(default_factory=list)
    coping_mechanisms: List[str] = Field(default_factory=list)


class EmotionalEntry(BaseModel):
    """Emotional state check-in entry"""
    user_profile_id: str
    conversation_id: str
    timestampISO: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    emotional_state: EmotionalState
    emotional_intensity: int = Field(..., ge=1, le=10)
    feelings: List[str] = Field(default_factory=list)
    comfort_level: Optional[int] = Field(None, ge=1, le=10)
    notes: Optional[str] = None
    source: str = SourceType.CHAT
    support_needed: bool = True


class WeeklyEmotionalSummary(BaseModel):
    """Weekly emotional wellness summary"""
    avgEmotionalWellness: float
    trend: Literal["improving", "declining", "stable"]
    avgComfortLevel: Optional[float] = None
    supportSessionsCount: int
    predominantEmotions: List[str] = Field(default_factory=list)
    week_start: str  # ISO date string
    week_end: str  # ISO date string
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ComfortEntry(BaseModel):
    """Comfort session tracking entry"""
    user_profile_id: str
    conversation_id: str
    timestampISO: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    comfort_type: str
    effectiveness: int = Field(..., ge=1, le=10)
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None


class ComfortSuggestion(BaseModel):
    """Comfort strategy suggestion"""
    id: str
    name: str
    description: str
    estimated_duration: str
    emotional_states: List[EmotionalState]  # Which states this helps with
    comfort_level: str  # gentle, moderate, intensive


class EmotionalPromptMapping(BaseModel):
    """Mapping of emotional states to appropriate prompts"""
    emotional_state: EmotionalState
    intensity_range: List[int]
    supportive_prompts: List[str]
    follow_up_questions: List[str]


class EmotionalAgentInstance(BaseModel):
    """Main document structure for a user's emotional agent instance"""
    user_profile_id: str
    agent_instance_id: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    
    # Arrays that will be appended to
    emotional_check_ins: List[Dict[str, Any]] = Field(default_factory=list)
    comfort_sessions: List[Dict[str, Any]] = Field(default_factory=list)
    emotional_trends: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Static arrays (rarely changed)
    comfort_suggestions: List[Dict[str, Any]] = Field(default_factory=list)
    emotional_prompt_mappings: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Current state
    last_check_in: Optional[str] = None  # ISO timestamp
    last_checkpoint: str = "GREETING"
    consecutive_support_days: int = 0
    total_comfort_sessions: int = 0
    
    # Emotional wellness tracking
    current_emotional_state: EmotionalState = EmotionalState.NEUTRAL
    emotional_wellness_score: float = 5.0  # 1-10 scale


class EmotionalRequest(BaseModel):
    """Input request schema for the emotional agent"""
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


class EmotionalResponse(BaseModel):
    """Output response schema for the emotional agent"""
    reply: str
    tool_call: Optional[ToolCall] = None
    conversation_id: str
    checkpoint: str
    context: Dict[str, Any] = Field(default_factory=dict)
    individual_id: Optional[str] = None
    user_profile_id: str
    agent_instance_id: str
    emotional_state_detected: Optional[EmotionalState] = None
    comfort_level_assessment: Optional[int] = None


class EmotionalAgentLog(BaseModel):
    """Lightweight log entry stored in the `emotional_agent` collection"""
    user_profile_id: str
    agent_instance_id: str
    conversation_id: str
    text: str
    checkpoint: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    emotional_intensity: int = EmotionalIntensity.MODERATE
    support_provided: bool = True
    timestampISO: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
