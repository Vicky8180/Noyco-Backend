# from typing import List, Optional
# from pydantic import BaseModel, Field, ConfigDict
# from datetime import datetime


# # ---------- Base Model for DB ----------
# class BaseDBModel(BaseModel):
#     model_config = ConfigDict(
#         json_encoders={
#             datetime: lambda v: v.isoformat()
#         }
#     )
    
#     created_at: datetime = Field(default_factory=datetime.utcnow)
#     updated_at: datetime = Field(default_factory=datetime.utcnow)


# # ---------- Shared Components ----------
# class LovedOne(BaseModel):
#     name: str
#     relation: Optional[str] = None
#     memories: Optional[List[str]] = Field(default_factory=list)


# class PastStory(BaseModel):
#     title: Optional[str] = None
#     description: str
#     date: Optional[datetime] = None
#     emotional_significance: Optional[str] = None  # e.g., happy, sad, proud


# # ---------- User Profile Schema ----------
# class UserProfile(BaseDBModel):
#     user_profile_id: str  # Unique identifier for this specific profile
#     role_entity_id: str  # Links multiple profiles to the same user
#     profile_name: str  # Name/label for this profile (e.g., "Work Profile", "Personal Profile")
#     name: str
#     age: Optional[int] = None
#     gender: Optional[str] = None
#     phone: str  # Required field
#     location: Optional[str] = None
#     language: Optional[str] = None
    
#     hobbies: Optional[List[str]] = Field(default_factory=list)
#     hates: Optional[List[str]] = Field(default_factory=list)
#     interests: Optional[List[str]] = Field(default_factory=list)
    
#     loved_ones: Optional[List[LovedOne]] = Field(default_factory=list)
#     past_stories: Optional[List[PastStory]] = Field(default_factory=list)
    
#     preferences: Optional[dict] = Field(default_factory=dict)  # e.g., call_time, tone, voice_gender
#     personality_traits: Optional[List[str]] = Field(default_factory=list)  # e.g., introvert, optimistic
    
#     health_info: Optional[dict] = Field(default_factory=dict)  # For elderly or therapy use cases
#     emotional_baseline: Optional[str] = None  # e.g., calm, anxious
#     is_active: bool = True  # Whether this profile is currently active


# # ---------- Request Schemas ----------
# class CreateUserProfileRequest(BaseModel):
#     profile_name: str  # Name/label for this profile
#     name: str
#     age: Optional[int] = None
#     gender: Optional[str] = None
#     phone: str  # Required field
#     location: Optional[str] = None
#     language: Optional[str] = None
    
#     hobbies: Optional[List[str]] = Field(default_factory=list)
#     hates: Optional[List[str]] = Field(default_factory=list)
#     interests: Optional[List[str]] = Field(default_factory=list)
    
#     loved_ones: Optional[List[LovedOne]] = Field(default_factory=list)
#     past_stories: Optional[List[PastStory]] = Field(default_factory=list)
    
#     preferences: Optional[dict] = Field(default_factory=dict)
#     personality_traits: Optional[List[str]] = Field(default_factory=list)
    
#     health_info: Optional[dict] = Field(default_factory=dict)
#     emotional_baseline: Optional[str] = None


# class UpdateUserProfileRequest(BaseModel):
#     profile_name: Optional[str] = None  # Allow updating profile name
#     name: Optional[str] = None
#     age: Optional[int] = None
#     gender: Optional[str] = None
#     phone: Optional[str] = None
#     location: Optional[str] = None
#     language: Optional[str] = None
    
#     hobbies: Optional[List[str]] = None
#     hates: Optional[List[str]] = None
#     interests: Optional[List[str]] = None
    
#     loved_ones: Optional[List[LovedOne]] = None
#     past_stories: Optional[List[PastStory]] = None
    
#     preferences: Optional[dict] = None
#     personality_traits: Optional[List[str]] = None
    
#     health_info: Optional[dict] = None
#     emotional_baseline: Optional[str] = None
#     is_active: Optional[bool] = None


# # ---------- Response Schemas ----------
# class UserProfileResponse(BaseModel):
#     user_profile_id: str
#     role_entity_id: str
#     profile_name: str
#     name: str
#     age: Optional[int] = None
#     gender: Optional[str] = None
#     phone: Optional[str] = None  # Optional in response for backward compatibility
#     location: Optional[str] = None
#     language: Optional[str] = None
    
#     hobbies: List[str] = Field(default_factory=list)
#     hates: List[str] = Field(default_factory=list)
#     interests: List[str] = Field(default_factory=list)
    
#     loved_ones: List[LovedOne] = Field(default_factory=list)
#     past_stories: List[PastStory] = Field(default_factory=list)
    
#     preferences: dict = Field(default_factory=dict)
#     personality_traits: List[str] = Field(default_factory=list)
    
#     health_info: dict = Field(default_factory=dict)
#     emotional_baseline: Optional[str] = None
#     is_active: bool = True
    
#     created_at: datetime
#     updated_at: datetime


# class UserProfileListResponse(BaseModel):
#     profiles: List[UserProfileResponse]
#     total_count: int
#     updated_at: datetime









from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import uuid4
import random


# ---------- Base Model for DB ----------
class BaseDBModel(BaseModel):
    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------- Shared Components ----------
class LovedOne(BaseModel):
    name: str
    relation: Optional[str] = None
    memories: List[str] = Field(default_factory=list)


class PastStory(BaseModel):
    title: Optional[str] = None
    description: str
    date: Optional[datetime] = None
    emotional_significance: Optional[str] = None  # e.g., happy, sad, proud


class CheckIn(BaseModel):
    date: datetime
    response: str
    completed: bool = True
    notes: Optional[str] = None


class MoodLog(BaseModel):
    date: datetime
    mood: str
    stress_level: Optional[int] = Field(None, ge=1, le=10)
    notes: Optional[str] = None


class ProgressEntry(BaseModel):
    date: datetime
    loneliness_score: Optional[float] = Field(None, ge=0.0, le=10.0)
    social_engagement_score: Optional[float] = Field(None, ge=0.0, le=10.0)
    affirmation: Optional[str] = None
    emotional_trend: Optional[str] = Field(None, pattern="^(improving|declining|stable)$")
    notes: Optional[str] = None


# ---------- User Profile Schema ----------
class UserProfile(BaseDBModel):
    user_profile_id: str  # Unique identifier
    role_entity_id: str  # Links multiple profiles to same user
    profile_name: str
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    phone: str
    location: Optional[str] = None
    language: Optional[str] = None

    hobbies: List[str] = Field(default_factory=list)
    hates: List[str] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)

    loved_ones: List[LovedOne] = Field(default_factory=list)
    past_stories: List[PastStory] = Field(default_factory=list)

    preferences: Dict[str, Any] = Field(default_factory=dict)
    personality_traits: List[str] = Field(default_factory=list)

    health_info: Dict[str, Any] = Field(default_factory=dict)
    emotional_baseline: Optional[str] = None
    is_active: bool = True


# ---------- Request Schemas ----------
class CreateUserProfileRequest(BaseModel):
    profile_name: str
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    phone: str
    location: Optional[str] = None
    language: Optional[str] = None

    hobbies: List[str] = Field(default_factory=list)
    hates: List[str] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)

    loved_ones: List[LovedOne] = Field(default_factory=list)
    past_stories: List[PastStory] = Field(default_factory=list)

    preferences: Dict[str, Any] = Field(default_factory=dict)
    personality_traits: List[str] = Field(default_factory=list)

    health_info: Dict[str, Any] = Field(default_factory=dict)
    emotional_baseline: Optional[str] = None


class UpdateUserProfileRequest(BaseModel):
    profile_name: Optional[str] = None
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    language: Optional[str] = None

    hobbies: Optional[List[str]] = None
    hates: Optional[List[str]] = None
    interests: Optional[List[str]] = None

    loved_ones: Optional[List[LovedOne]] = None
    past_stories: Optional[List[PastStory]] = None

    preferences: Optional[Dict[str, Any]] = None
    personality_traits: Optional[List[str]] = None

    health_info: Optional[Dict[str, Any]] = None
    emotional_baseline: Optional[str] = None
    is_active: Optional[bool] = None


# ---------- Response Schemas ----------
class UserProfileResponse(BaseModel):
    user_profile_id: str
    role_entity_id: str
    profile_name: str
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    language: Optional[str] = None

    hobbies: List[str] = Field(default_factory=list)
    hates: List[str] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)

    loved_ones: List[LovedOne] = Field(default_factory=list)
    past_stories: List[PastStory] = Field(default_factory=list)

    preferences: Dict[str, Any] = Field(default_factory=dict)
    personality_traits: List[str] = Field(default_factory=list)

    health_info: Dict[str, Any] = Field(default_factory=dict)
    emotional_baseline: Optional[str] = None
    is_active: bool = True

    created_at: datetime
    updated_at: datetime


class UserProfileListResponse(BaseModel):
    profiles: List[UserProfileResponse]
    total_count: int
    updated_at: datetime


# ---------- Goal ID Generators ----------
def generate_emotional_goal_id() -> str:
    return f"emotional_{random.randint(100, 999)}"

def generate_accountability_goal_id() -> str:
    return f"accountability_{random.randint(100, 999)}"

def generate_anxiety_goal_id() -> str:
    return f"anxiety_{random.randint(100, 999)}"

def generate_therapy_goal_id() -> str:
    return f"therapy_{random.randint(100, 999)}"

def generate_loneliness_goal_id() -> str:
    return f"loneliness_{random.randint(100, 999)}"


# ---------- Base Goal ----------
class BaseGoal(BaseModel):
    goal_id: str
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    status: str = Field(default="active", pattern="^(active|paused|completed|dropped)$")

    check_ins: List[CheckIn] = Field(default_factory=list)
    streak: int = Field(default=0, ge=0)
    max_streak: int = Field(default=0, ge=0)
    progress_tracking: List[ProgressEntry] = Field(default_factory=list)
    mood_trend: List[MoodLog] = Field(default_factory=list)


# ---------- Agents ----------

# 1. Emotional Companion Agent
class EmotionalGoal(BaseGoal):
    goal_id: str = Field(default_factory=generate_emotional_goal_id)


class EmotionalCompanionAgent(BaseDBModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_profile_id: str
    memory_stack: List[str] = Field(default_factory=list)
    comfort_tips: List[str] = Field(default_factory=list)
    emotional_goals: List[EmotionalGoal] = Field(default_factory=list)  # Changed to List
    last_interaction: Optional[datetime] = None


# 2. Accountability Buddy Agent
class AccountabilityGoal(BaseGoal):
    goal_id: str = Field(default_factory=generate_accountability_goal_id)


class AccountabilityAgent(BaseDBModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_profile_id: str
    accountability_goals: List[AccountabilityGoal] = Field(default_factory=list)
    last_interaction: Optional[datetime] = None


# 3. Social Anxiety Agent
class AnxietyGoal(BaseGoal):
    goal_id: str = Field(default_factory=generate_anxiety_goal_id)
    event_date: Optional[datetime] = None
    event_type: Optional[str] = None
    anxiety_level: Optional[int] = Field(None, ge=1, le=10)
    nervous_thoughts: List[str] = Field(default_factory=list)
    physical_symptoms: List[str] = Field(default_factory=list)


class SocialAnxietyAgent(BaseDBModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_profile_id: str
    anxiety_goals: List[AnxietyGoal] = Field(default_factory=list)
    last_interaction: Optional[datetime] = None


# 4. Therapy Agent
class TherapyGoal(BaseGoal):
    goal_id: str = Field(default_factory=generate_therapy_goal_id)


class TherapyAgent(BaseDBModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_profile_id: str
    therapy_goals: List[TherapyGoal] = Field(default_factory=list)
    last_interaction: Optional[datetime] = None


# 5. Loneliness Agent
class LonelinessGoal(BaseGoal):
    goal_id: str = Field(default_factory=generate_loneliness_goal_id)


class LonelinessAgent(BaseDBModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_profile_id: str
    loneliness_goals: List[LonelinessGoal] = Field(default_factory=list)
    last_interaction: Optional[datetime] = None


# ---------- Goal Update Request Schemas ----------
class UpdateEmotionalGoalRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    status: Optional[str] = Field(None, pattern="^(active|paused|completed|dropped)$")
    memory_stack: Optional[List[str]] = None
    comfort_tips: Optional[List[str]] = None


class UpdateAccountabilityGoalRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    status: Optional[str] = Field(None, pattern="^(active|paused|completed|dropped)$")


class UpdateAnxietyGoalRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    status: Optional[str] = Field(None, pattern="^(active|paused|completed|dropped)$")
    event_date: Optional[datetime] = None
    event_type: Optional[str] = None
    anxiety_level: Optional[int] = Field(None, ge=1, le=10)
    nervous_thoughts: Optional[List[str]] = None
    physical_symptoms: Optional[List[str]] = None


class UpdateTherapyGoalRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    status: Optional[str] = Field(None, pattern="^(active|paused|completed|dropped)$")


class UpdateLonelinessGoalRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    status: Optional[str] = Field(None, pattern="^(active|paused|completed|dropped)$")


# ---------- Utility ----------
def update_timestamp(model_instance: BaseDBModel) -> BaseDBModel:
    model_instance.updated_at = datetime.utcnow()
    return model_instance
