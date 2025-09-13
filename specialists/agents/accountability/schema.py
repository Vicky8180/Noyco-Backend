"""
Schema definitions for Accountability Buddy Agent
Supports goal tracking, daily check-ins, progress monitoring, and streak management
"""

from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional, Any, Literal
from datetime import datetime, date, timedelta
from enum import Enum

# === ENUMS ===

class GoalCategory(str, Enum):
    """Categories of accountability goals"""
    HEALTH_FITNESS = "health_fitness"
    SOBRIETY = "sobriety" 
    MENTAL_HEALTH = "mental_health"
    CAREER = "career"
    RELATIONSHIPS = "relationships"
    HABITS = "habits"
    LOCATION_CHANGE = "location_change"
    THERAPY = "therapy"
    MEDITATION = "meditation"
    OTHER = "other"

class GoalStatus(str, Enum):
    """Current status of a goal"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

class CheckInType(str, Enum):
    """Types of daily check-ins"""
    MORNING = "morning"
    EVENING = "evening"
    CUSTOM = "custom"

class ResponseType(str, Enum):
    """Types of user responses to check-ins"""
    YES_NO = "yes_no"
    RATING = "rating"  # 1-10 scale
    TEXT = "text"
    MULTIPLE_CHOICE = "multiple_choice"

class ProgressLevel(str, Enum):
    """Progress assessment levels"""
    EXCELLENT = "excellent"    # 90-100%
    GOOD = "good"             # 70-89%
    FAIR = "fair"             # 50-69%
    STRUGGLING = "struggling"  # 30-49%
    DIFFICULT = "difficult"   # 0-29%

class CheckpointState(str, Enum):
    """Conversation flow checkpoints/states"""
    GREETING = "GREETING"
    GOAL_CREATION = "GOAL_CREATION"
    DAILY_CHECKIN = "DAILY_CHECKIN"
    RATING_RESPONSE = "RATING_RESPONSE"
    YES_NO_RESPONSE = "YES_NO_RESPONSE"
    PROGRESS_REVIEW = "PROGRESS_REVIEW"
    MOTIVATION_REQUEST = "MOTIVATION_REQUEST"
    GOAL_MODIFICATION = "GOAL_MODIFICATION"
    STREAK_CELEBRATION = "STREAK_CELEBRATION"
    CLOSING = "CLOSING"

# === CORE DATA MODELS ===

class GoalMetric(BaseModel):
    """Defines how to measure goal progress"""
    name: str = Field(..., description="Name of the metric (e.g., 'Water intake', 'Meditation minutes')")
    type: ResponseType = Field(..., description="How user will respond")
    target_value: Optional[float] = Field(None, description="Target value for ratings (e.g., 8/10)")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    question: str = Field(..., description="Question to ask user")

class AccountabilityGoal(BaseModel):
    """Main goal definition for accountability tracking"""
    goal_id: str = Field(..., description="Unique identifier for the goal")
    user_profile_id: str = Field(..., description="User profile ID who owns this goal")
    title: str = Field(..., description="Goal title (e.g., 'Stay Sober')")
    description: str = Field(..., description="Detailed goal description")
    category: GoalCategory = Field(..., description="Goal category")
    
    # Tracking configuration
    metrics: List[GoalMetric] = Field(default_factory=list, description="How to measure progress")
    check_in_frequency: List[CheckInType] = Field(default_factory=list, description="When to check in")
    reminder_times: List[str] = Field(default_factory=list, description="Times for reminders (HH:MM format)")
    
    # Timeline
    start_date: date = Field(default_factory=date.today)
    target_end_date: Optional[date] = Field(None, description="When goal should be achieved")
    
    # Status
    status: GoalStatus = Field(default=GoalStatus.ACTIVE)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Motivation
    motivation: Optional[str] = Field(None, description="Why this goal matters to the user")
    rewards: List[str] = Field(default_factory=list, description="Planned rewards for milestones")

class CheckInResponse(BaseModel):
    """User's response to a daily check-in"""
    metric_name: str = Field(..., description="Which metric this response is for")
    response_type: ResponseType = Field(..., description="Type of response")
    
    # Response values (only one should be populated based on type)
    yes_no_value: Optional[bool] = Field(None, description="For yes/no questions")
    rating_value: Optional[int] = Field(None, ge=1, le=10, description="For 1-10 ratings")
    text_value: Optional[str] = Field(None, description="For text responses")
    choice_value: Optional[str] = Field(None, description="For multiple choice")
    
    notes: Optional[str] = Field(None, description="Additional user notes")

class DailyCheckIn(BaseModel):
    """Record of a daily accountability check-in"""
    checkin_id: str = Field(..., description="Unique check-in identifier")
    goal_id: str = Field(..., description="Associated goal")
    user_profile_id: str = Field(..., description="User performing check-in")
    conversation_id: str = Field(..., description="Conversation context")
    
    # Check-in details
    checkin_date: date = Field(default_factory=date.today)
    checkin_type: CheckInType = Field(..., description="Morning, evening, or custom")
    responses: List[CheckInResponse] = Field(default_factory=list)
    
    # Calculated metrics
    overall_score: Optional[float] = Field(None, description="Calculated daily score (0-10)")
    progress_level: Optional[ProgressLevel] = Field(None, description="Progress assessment")
    
    # Metadata
    completed_at: datetime = Field(default_factory=datetime.utcnow)
    agent_response: Optional[str] = Field(None, description="Agent's encouraging response")

class AccountabilitySession(BaseModel):
    """Session state for accountability conversations"""
    session_id: str = Field(..., description="Unique session identifier")
    user_profile_id: str = Field(..., description="User profile ID")
    conversation_id: str = Field(..., description="Conversation ID")
    goal_id: Optional[str] = Field(None, description="Current goal being worked on")
    
    # Session state
    current_checkpoint: CheckpointState = Field(default=CheckpointState.GREETING)
    last_interaction: datetime = Field(default_factory=datetime.utcnow)
    
    # Conversation context
    context: Dict[str, Any] = Field(default_factory=dict)
    pending_responses: List[str] = Field(default_factory=list)
    
    # Session metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(None)

class ProgressStreak(BaseModel):
    """Tracks streaks and milestones for goals"""
    goal_id: str = Field(..., description="Associated goal")
    user_profile_id: str = Field(..., description="Goal owner")
    
    # Streak tracking
    current_streak: int = Field(default=0, description="Current consecutive days")
    longest_streak: int = Field(default=0, description="Best streak achieved")
    total_successful_days: int = Field(default=0, description="Total days with success")
    total_days_tracked: int = Field(default=0, description="Total days since start")
    
    # Milestone tracking
    milestones_reached: List[str] = Field(default_factory=list, description="Achieved milestones")
    next_milestone: Optional[str] = Field(None, description="Next milestone to reach")
    
    # Recent performance
    last_7_days_score: Optional[float] = Field(None, description="Average score last 7 days")
    last_30_days_score: Optional[float] = Field(None, description="Average score last 30 days")
    
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# === COLLECTION SCHEMAS ===

class AccountabilityAgent(BaseModel):
    """Lightweight catalog entry for accountability agents"""
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(default="Accountability Buddy", description="Agent name")
    description: str = Field(default="Supports goal tracking and daily accountability", description="Agent description")
    type: str = Field(default="accountability_support", description="Agent type")
    agent_instance_id: str = Field(..., description="Reference to the agent instance")
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class AccountabilityAgentInstance(BaseModel):
    """Main document structure for a user's accountability agent instance"""
    agent_instance_id: str = Field(..., description="Unique instance identifier")
    user_profile_id: str = Field(..., description="User profile ID")
    individual_id: Optional[str] = Field(None, description="Individual ID reference")
    
    # Core accountability data
    goals: List[Dict[str, Any]] = Field(default_factory=list, description="User's accountability goals")
    checkins: List[Dict[str, Any]] = Field(default_factory=list, description="Daily check-in records")
    goal_streaks: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Streak data per goal")
    
    # Progress tracking
    total_goals_created: int = Field(default=0, description="Total goals ever created")
    total_checkins: int = Field(default=0, description="Total check-ins completed")
    total_successful_days: int = Field(default=0, description="Total successful days across all goals")
    average_success_rate: float = Field(default=0.0, description="Overall success rate")
    longest_overall_streak: int = Field(default=0, description="Longest streak across all goals")
    current_overall_streak: int = Field(default=0, description="Current streak across all goals")
    
    # Session state
    last_check_in: Optional[str] = Field(None, description="Last check-in timestamp")
    last_checkpoint: str = Field(default=CheckpointState.GREETING, description="Last conversation checkpoint")
    preferred_checkin_time: Optional[str] = Field(None, description="User's preferred check-in time")
    
    # Engagement metrics
    total_conversations: int = Field(default=0, description="Total conversations with agent")
    last_interaction: Optional[str] = Field(None, description="Last interaction timestamp")
    
    # Personalization data
    communication_preferences: Dict[str, Any] = Field(default_factory=dict, description="How user likes to communicate")
    motivation_triggers: List[str] = Field(default_factory=list, description="What motivates this user")
    struggle_patterns: List[str] = Field(default_factory=list, description="Common struggle areas")
    success_patterns: List[str] = Field(default_factory=list, description="What helps user succeed")
    
    # Milestone tracking
    milestones_achieved: List[Dict[str, Any]] = Field(default_factory=list, description="Major milestones reached")
    
    # Agent learning data
    effective_responses: List[str] = Field(default_factory=list, description="Response types that work well")
    preferred_encouragement_style: Optional[str] = Field(None, description="User's preferred encouragement style")
    goal_categories_affinity: Dict[str, float] = Field(default_factory=dict, description="Success rates by category")
    
    # Timestamps
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

# === REQUEST/RESPONSE SCHEMAS ===

class AccountabilityRequest(BaseModel):
    """Input request schema for the accountability agent"""
    text: str = Field(..., description="User query or message")
    conversation_id: str = Field(..., description="Unique ID of the ongoing conversation")
    checkpoint: Optional[str] = Field(None, description="Current checkpoint/state in the conversation flow")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context (metadata, history, session info)")
    individual_id: Optional[str] = Field(None, description="Reference to the individual agent instance")
    user_profile_id: str = Field(..., description="ID of the user's profile (used to fetch complete user context)")
    agent_instance_id: str = Field(..., description="ID of the agent instance collection (tracks goals, progress, and updates)")

class AccountabilityResponse(BaseModel):
    """Output response schema for the accountability agent"""
    reply: str = Field(..., description="Agent's response to user")
    tool_call: Optional[Dict[str, Any]] = Field(None, description="Tool call if needed")
    conversation_id: str = Field(..., description="Conversation ID")
    checkpoint: str = Field(..., description="Current checkpoint state")
    context: Dict[str, Any] = Field(default_factory=dict, description="Updated context")
    individual_id: Optional[str] = Field(None, description="Individual ID reference")
    user_profile_id: str = Field(..., description="User profile ID")
    agent_instance_id: str = Field(..., description="Agent instance ID")

class AccountabilityAgentLog(BaseModel):
    """Lightweight log entry stored in the `accountability_agent` collection"""
    user_profile_id: str
    agent_instance_id: str
    conversation_id: str
    text: str
    checkpoint: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    goal_updates: List[str] = Field(default_factory=list, description="Goals that were modified")
    checkin_completed: bool = Field(default=False, description="Whether check-in was completed")
    timestampISO: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

# === GOAL TEMPLATES ===

GOAL_TEMPLATES = {
    "sobriety": {
        "title": "Stay Sober",
        "description": "Maintain sobriety and build healthy habits",
        "category": GoalCategory.SOBRIETY,
        "metrics": [
            GoalMetric(name="stayed_sober", type=ResponseType.YES_NO, question="Did you stay sober today?"),
            GoalMetric(name="cravings_level", type=ResponseType.RATING, question="How strong were any cravings today? (1-10)", target_value=3.0),
            GoalMetric(name="support_used", type=ResponseType.YES_NO, question="Did you use your support system today?")
        ],
        "reminder_times": ["09:00", "20:00"],
        "motivation_prompts": [
            "Remember why you started this journey",
            "Each sober day is a victory",
            "You're building a healthier, stronger you"
        ]
    },
    "meditation": {
        "title": "Daily Meditation",
        "description": "Build a consistent meditation practice",
        "category": GoalCategory.MEDITATION,
        "metrics": [
            GoalMetric(name="meditated", type=ResponseType.YES_NO, question="Did you meditate today?"),
            GoalMetric(name="duration_minutes", type=ResponseType.RATING, question="How many minutes did you meditate? (rate 1-10 for 1-30+ mins)", target_value=5.0),
            GoalMetric(name="mindfulness_level", type=ResponseType.RATING, question="How mindful did you feel today? (1-10)", target_value=7.0)
        ],
        "reminder_times": ["08:00", "18:00"],
        "motivation_prompts": [
            "Even 5 minutes of meditation counts",
            "Your mind deserves this peaceful moment",
            "Consistency matters more than duration"
        ]
    },
    "fitness": {
        "title": "Daily Exercise",
        "description": "Maintain regular physical activity",
        "category": GoalCategory.HEALTH_FITNESS,
        "metrics": [
            GoalMetric(name="exercised", type=ResponseType.YES_NO, question="Did you exercise today?"),
            GoalMetric(name="intensity_level", type=ResponseType.RATING, question="How intense was your workout? (1-10)", target_value=6.0),
            GoalMetric(name="energy_after", type=ResponseType.RATING, question="How energized do you feel? (1-10)", target_value=7.0)
        ],
        "reminder_times": ["07:00", "17:00"],
        "motivation_prompts": [
            "Your body is capable of amazing things",
            "Every workout makes you stronger",
            "Movement is medicine for your mind and body"
        ]
    }
}
