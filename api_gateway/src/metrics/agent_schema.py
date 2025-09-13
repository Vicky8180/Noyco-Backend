from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class GoalMetricSchema(BaseModel):
    goal_id: str
    title: str
    description: str
    due_date: Optional[datetime] = None
    status: str
    streak: int
    max_streak: int
    check_ins_count: int
    progress_percentage: float
    days_active: int
    days_until_due: Optional[int] = None
    mood_average: Optional[float] = None
    last_check_in: Optional[datetime] = None

class AgentGoalSummarySchema(BaseModel):
    agent_type: str
    agent_id: str
    user_profile_id: str
    total_goals: int
    active_goals: int
    completed_goals: int
    goals: List[GoalMetricSchema]
    last_interaction: Optional[datetime] = None
    created_at: datetime

class AgentMetricsResponseSchema(BaseModel):
    individual_id: str
    agent_type: str
    timeframe: str
    agents: List[AgentGoalSummarySchema]
    summary: Dict[str, Any]

class AgentTypeOptionSchema(BaseModel):
    agent_type: str
    display_name: str
    count: int
    total_goals: int

class GoalProgressDataSchema(BaseModel):
    goal_id: str
    title: str
    progress_data: List[Dict[str, Any]]  # Time series data for charts
    check_in_frequency: Dict[str, int]  # Daily check-in patterns
    mood_trend: List[Dict[str, Any]]  # Mood tracking over time
    streak_history: List[Dict[str, Any]]  # Streak progression
