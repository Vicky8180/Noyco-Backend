"""
Schema definitions for Therapy (Mental Health) Check-In Agent
Supports mood tracking, relaxation tools, and weekly trend reporting
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Literal
from datetime import datetime, date
from enum import Enum


class RiskLevel(int, Enum):
    """Risk levels for user safety monitoring"""
    NONE = 0
    LOW = 1
    MODERATE = 2
    HIGH = 3


class CheckpointState(str, Enum):
    """Conversation flow checkpoints/states"""
    GREETING = "GREETING"
    ASKED_MOOD_RATING = "ASKED_MOOD_RATING"
    ASK_FEELINGS = "ASK_FEELINGS"
    OFFER_EXERCISE = "OFFER_EXERCISE"
    BREATHING_SESSION_RUNNING = "BREATHING_SESSION_RUNNING"
    LOGGING_ENTRY = "LOGGING_ENTRY"
    CHECKIN_SUMMARY = "CHECKIN_SUMMARY"
    CLOSING = "CLOSING"
    CRISIS_ESCALATION = "CRISIS_ESCALATION"


class SourceType(str, Enum):
    """Source of the check-in"""
    CHAT = "chat"
    CALL = "call"
    SCHEDULED = "scheduled"


class ConsentSettings(BaseModel):
    """User consent settings"""
    voice_analysis: bool = False
    data_use: bool = True


class CheckInPreferences(BaseModel):
    """User check-in preferences"""
    days: List[int] = Field(default_factory=lambda: [0, 2, 4])  # Mon, Wed, Fri by default
    hour24: int = 9  # 9 AM by default


class UserProfile(BaseModel):
    """User profile data"""
    userId: str
    name: str
    locale: str = "en-US"
    timezone: str = "America/New_York"
    consent: ConsentSettings = Field(default_factory=ConsentSettings)
    checkInPreferences: CheckInPreferences = Field(default_factory=CheckInPreferences)


class MoodEntry(BaseModel):
    """Mood check-in entry"""
    user_profile_id: str
    conversation_id: str
    timestampISO: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    moodScore: int = Field(..., ge=1, le=10)
    feelings: List[str] = Field(default_factory=list)
    stress_score: Optional[int] = Field(None, ge=0, le=10)
    voiceStress: Optional[int] = Field(None, ge=0, le=100)
    notes: Optional[str] = None
    source: str = SourceType.CHAT
    riskLevel: int = RiskLevel.NONE


class WeeklySummary(BaseModel):
    """Weekly mood summary"""
    avgMood: float
    trend: Literal["up", "down", "flat"]
    avgStress: Optional[float] = None
    streakDays: int
    notes: List[str] = Field(default_factory=list)
    week_start: str  # ISO date string
    week_end: str  # ISO date string
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ProgressEntry(BaseModel):
    """Progress tracking entry"""
    user_profile_id: str
    conversation_id: str
    timestampISO: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    strategy: str
    effectiveness: int = Field(..., ge=1, le=10)
    notes: Optional[str] = None


class CopingSuggestion(BaseModel):
    """Coping strategy suggestion"""
    id: str
    name: str
    description: str
    duration_minutes: int
    mood_range: List[int]  # e.g., [1, 4] for low moods
    tags: List[str]


class MoodPromptMapping(BaseModel):
    """Mapping of mood scores to appropriate prompts"""
    mood_range: List[int]
    prompts: List[str]
    follow_up_questions: List[str]


class TherapyAgentInstance(BaseModel):
    """Main document structure for a user's therapy agent instance"""
    user_profile_id: str
    agent_instance_id: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    
    # Arrays that will be appended to
    daily_check_ins: List[Dict[str, Any]] = Field(default_factory=list)
    progress_tracking: List[Dict[str, Any]] = Field(default_factory=list)
    mood_trends: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Static arrays (rarely changed)
    coping_suggestions: List[Dict[str, Any]] = Field(default_factory=list)
    mood_prompt_mappings: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Current state
    last_check_in: Optional[str] = None  # ISO timestamp
    last_checkpoint: str = CheckpointState.GREETING
    streak_days: int = 0
    total_check_ins: int = 0


class TherapyRequest(BaseModel):
    """Input request schema for the therapy agent"""
    text: str
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


class TherapyResponse(BaseModel):
    """Output response schema for the therapy agent"""
    reply: str
    tool_call: Optional[ToolCall] = None
    conversation_id: str
    checkpoint: str
    context: Dict[str, Any] = Field(default_factory=dict)
    individual_id: Optional[str] = None
    user_profile_id: str
    agent_instance_id: str


class TherapyAgentLog(BaseModel):
    """Lightweight log entry stored in the `therapy_agent` collection"""
    user_profile_id: str
    agent_instance_id: str
    conversation_id: str
    text: str
    checkpoint: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    riskLevel: int = RiskLevel.NONE
    timestampISO: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
