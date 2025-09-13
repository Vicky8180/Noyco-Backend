"""
Unified Schema for All Specialized Agents
Contains shared models and agent-specific schemas for emotional, accountability, anxiety, therapy, and loneliness agents.
"""

# ---------- Base Model for DB ----------
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import uuid4
import random

# ---------- ID Generation Functions ----------
def generate_emotional_goal_id() -> str:
    """Generate unique ID for emotional goals: emotional_001, emotional_002, etc."""
    return f"emotional_{random.randint(100, 999)}"

def generate_accountability_goal_id() -> str:
    """Generate unique ID for accountability goals: accountability_001, accountability_002, etc."""
    return f"accountability_{random.randint(100, 999)}"

def generate_anxiety_goal_id() -> str:
    """Generate unique ID for anxiety goals: anxiety_001, anxiety_002, etc."""
    return f"anxiety_{random.randint(100, 999)}"

def generate_therapy_goal_id() -> str:
    """Generate unique ID for therapy goals: therapy_001, therapy_002, etc."""
    return f"therapy_{random.randint(100, 999)}"

def generate_loneliness_goal_id() -> str:
    """Generate unique ID for loneliness goals: loneliness_001, loneliness_002, etc."""
    return f"loneliness_{random.randint(100, 999)}"
class BaseDBModel(BaseModel):
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        # Allow field updates for updated_at
        validate_assignment = True


# ---------- Shared Components ----------
class LovedOne(BaseModel):
    name: str
    relation: Optional[str] = None
    memories: List[str] = Field(default_factory=list)  # Fixed: removed Optional


class PastStory(BaseModel):
    title: Optional[str] = None
    description: str
    date: Optional[datetime] = None
    emotional_significance: Optional[str] = None  # e.g., happy, sad, proud


class CheckIn(BaseModel):
    date: datetime
    response: str
    completed: bool = False  # Default to False since response is provided
    notes: Optional[str] = None


class MoodLog(BaseModel):
    date: datetime
    mood: str
    stress_level: Optional[int] = Field(None, ge=1, le=10)  # Added validation
    notes: Optional[str] = None


class ProgressEntry(BaseModel):
    date: datetime
    loneliness_score: Optional[float] = Field(None, ge=0.0, le=10.0)  # Added validation
    social_engagement_score: Optional[float] = Field(None, ge=0.0, le=10.0)  # Added validation
    affirmation: Optional[str] = None
    emotional_trend: Optional[str] = Field(None, pattern="^(improving|declining|stable)$")  # Added validation
    notes: Optional[str] = None


# ---------- User Profile Schema ----------
class UserProfile(BaseDBModel):
    user_profile_id: str = Field(default_factory=lambda: str(uuid4()))  # Auto-generate ID
    user_id: str  # Link to authentication system
    profile_name: str
    name: str
    age: Optional[int] = Field(None, gt=0, le=150)  # Added realistic age constraints
    gender: Optional[str] = None
    location: Optional[str] = None
    language: Optional[str] = "en"  # Default language
    hobbies: List[str] = Field(default_factory=list)  # Fixed: removed Optional
    hates: List[str] = Field(default_factory=list)  # Fixed: removed Optional
    interests: List[str] = Field(default_factory=list)  # Fixed: removed Optional
    loved_ones: List[LovedOne] = Field(default_factory=list)  # Fixed: removed Optional
    past_stories: List[PastStory] = Field(default_factory=list)  # Fixed: removed Optional
    personality_traits: List[str] = Field(default_factory=list)  # Fixed: removed Optional
    health_info: Dict[str, Any] = Field(default_factory=dict)  # Fixed: removed Optional, added typing
    is_active: bool = True


# ---------- Base Goal Class ----------
class BaseGoal(BaseModel):
    goal_id: str  # Will be set by subclasses with specific generators
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    status: str = Field(default="active", pattern="^(active|paused|completed|dropped)$")
    
    # Tracking
    check_ins: List[CheckIn] = Field(default_factory=list)
    streak: int = Field(default=0, ge=0)
    max_streak: int = Field(default=0, ge=0)
    progress_tracking: List[ProgressEntry] = Field(default_factory=list)
    mood_trend: List[MoodLog] = Field(default_factory=list)  # Fixed: removed Optional


# ---------- Agents ----------

# 1. Emotional Companion Agent
class EmotionalGoal(BaseGoal):
    goal_id: str = Field(default_factory=generate_emotional_goal_id)
    
    class Config:
        # Allow the default factory to work properly
        validate_assignment = True


class EmotionalCompanionAgent(BaseDBModel):
    agent_instance_id: str = Field(default_factory=lambda: str(uuid4()))
    user_profile_id: str
    memory_stack: List[str] = Field(default_factory=list)
    comfort_tips: List[str] = Field(default_factory=list)
    emotional_goals: Optional[EmotionalGoal] = None
    last_interaction: Optional[datetime] = None


# 2. Accountability Buddy Agent (multi-instance)
class AccountabilityGoal(BaseGoal):
    goal_id: str = Field(default_factory=generate_accountability_goal_id)
    
    class Config:
        validate_assignment = True


class AccountabilityAgent(BaseDBModel):
    agent_instance_id: str = Field(default_factory=lambda: str(uuid4()))
    user_profile_id: str
    accountability_goals: List[AccountabilityGoal] = Field(default_factory=list)
    last_interaction: Optional[datetime] = None


# 3. Social Anxiety / Pre-Event Prep Agent (multi-instance)
class AnxietyGoal(BaseGoal):
    goal_id: str = Field(default_factory=generate_anxiety_goal_id)
    
    # Event details
    event_date: Optional[datetime] = None
    event_type: Optional[str] = None  # e.g., "meeting", "exam", "presentation"
    
    # Anxiety tracking
    anxiety_level: Optional[int] = Field(None, ge=1, le=10)  # Added validation
    nervous_thoughts: List[str] = Field(default_factory=list)
    physical_symptoms: List[str] = Field(default_factory=list)
    
    class Config:
        validate_assignment = True


class SocialAnxietyAgent(BaseDBModel):
    agent_instance_id: str = Field(default_factory=lambda: str(uuid4()))
    user_profile_id: str
    anxiety_goals: List[AnxietyGoal] = Field(default_factory=list)
    last_interaction: Optional[datetime] = None


# 4. Therapy / Mental Health Check-In Bot
class TherapyGoal(BaseGoal):
    goal_id: str = Field(default_factory=generate_therapy_goal_id)
    
    class Config:
        validate_assignment = True


class TherapyAgent(BaseDBModel):
    agent_instance_id: str = Field(default_factory=lambda: str(uuid4()))
    user_profile_id: str
    therapy_goals: List[TherapyGoal] = Field(default_factory=list)  # Fixed: removed Optional
    last_interaction: Optional[datetime] = None


# 5. Loneliness / Passive Companion Agent
class LonelinessGoal(BaseGoal):
    goal_id: str = Field(default_factory=generate_loneliness_goal_id)
    
    class Config:
        validate_assignment = True


class LonelinessAgent(BaseDBModel):
    agent_instance_id: str = Field(default_factory=lambda: str(uuid4()))
    user_profile_id: str
    loneliness_goals: List[LonelinessGoal] = Field(default_factory=list)  # Fixed: removed Optional
    last_interaction: Optional[datetime] = None


# ---------- Utility Functions ----------
def update_timestamp(model_instance: BaseDBModel) -> BaseDBModel:
    """Helper function to update the updated_at timestamp"""
    model_instance.updated_at = datetime.utcnow()
    return model_instance
