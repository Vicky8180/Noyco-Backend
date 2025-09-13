from fastapi import HTTPException
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pymongo.database import Database
from pymongo import DESCENDING
from .agent_schema import (
    AgentMetricsResponseSchema,
    AgentGoalSummarySchema,
    GoalMetricSchema,
    AgentTypeOptionSchema,
    GoalProgressDataSchema
)

class AgentMetricsController:
    def __init__(self, db: Database):
        self.db = db
        self.conversations_collection = db.conversations
        # Agent collections
        self.agent_collections = {
            'accountability': db.accountability_agents,
            'loneliness': db.loneliness_agents,
            'therapy': db.therapy_agents
        }
        
        # Goal field mappings
        self.goal_fields = {
            'accountability': 'accountability_goals',
            'loneliness': 'loneliness_goals',
            'therapy': 'therapy_goals'
        }

    async def get_agent_types_options(self, individual_id: str) -> List[AgentTypeOptionSchema]:
        """Get available agent types with their counts and goal statistics"""
        try:
            agent_options = []
            
            for agent_type, collection in self.agent_collections.items():
                # Count agents for this user - we need to get user profile first
                sample_conv = self.conversations_collection.find_one({
                    "individual_id": individual_id
                })
                
                if not sample_conv:
                    continue
                    
                user_profile_id = sample_conv.get("user_profile_id")
                if not user_profile_id:
                    continue
                
                # Count agents for this user
                agent_count = collection.count_documents({
                    "user_profile_id": user_profile_id
                })
                
                if agent_count > 0:
                    # Get total goals for this agent type
                    pipeline = [
                        {"$match": {"user_profile_id": user_profile_id}},
                        {"$unwind": f"${self.goal_fields[agent_type]}"},
                        {"$group": {"_id": None, "total_goals": {"$sum": 1}}}
                    ]
                    
                    result = list(collection.aggregate(pipeline))
                    total_goals = result[0]["total_goals"] if result else 0
                    
                    display_names = {
                        'accountability': 'Accountability Agent',
                        'loneliness': 'Loneliness Agent', 
                        'therapy': 'Therapy Agent'
                    }
                    
                    agent_options.append(AgentTypeOptionSchema(
                        agent_type=agent_type,
                        display_name=display_names.get(agent_type, agent_type.title()),
                        count=agent_count,
                        total_goals=total_goals
                    ))
            
            return agent_options
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch agent types: {str(e)}")

    async def get_agent_metrics(
        self, 
        individual_id: str, 
        agent_type: str, 
        timeframe: str = "7d"
    ) -> AgentMetricsResponseSchema:
        """Get comprehensive metrics for a specific agent type"""
        try:
            if agent_type not in self.agent_collections:
                raise HTTPException(status_code=400, detail=f"Invalid agent type: {agent_type}")
            
            collection = self.agent_collections[agent_type]
            goal_field = self.goal_fields[agent_type]
            
            # Calculate date range based on timeframe
            end_date = datetime.utcnow()
            timeframe_days = {
                "1d": 1,
                "7d": 7, 
                "14d": 14,
                "30d": 30
            }
            
            days = timeframe_days.get(timeframe, 7)
            start_date = end_date - timedelta(days=days)
            
            # Find all agents for this user (we need to find user_profile_id first)
            # Get user profile from conversations or other collections
            sample_conv = self.conversations_collection.find_one({
                "individual_id": individual_id
            })
            
            if not sample_conv:
                raise HTTPException(status_code=404, detail="No user profile found")
            
            user_profile_id = sample_conv.get("user_profile_id")
            
            # Get agents for this user
            agents_cursor = collection.find({"user_profile_id": user_profile_id})
            agents = list(agents_cursor)
            
            agent_summaries = []
            total_goals = 0
            total_active = 0
            total_completed = 0
            
            for agent in agents:
                goals = agent.get(goal_field, [])
                goal_metrics = []
                
                active_goals = 0
                completed_goals = 0
                
                for goal in goals:
                    # Calculate goal metrics
                    check_ins = goal.get("check_ins", [])
                    progress_tracking = goal.get("progress_tracking", [])
                    mood_trend = goal.get("mood_trend", [])
                    
                    # Filter check-ins by timeframe - check-ins have 'date' field
                    recent_check_ins = [
                        ci for ci in check_ins 
                        if ci.get("date") and ci["date"] >= start_date and ci.get("completed", True)
                    ]
                    
                    # Calculate progress percentage from progress_tracking
                    progress_percentage = 0.0
                    if progress_tracking:
                        # Use the latest progress entry with loneliness_score or social_engagement_score
                        latest_progress = max(progress_tracking, key=lambda x: x.get("date", datetime.min))
                        if latest_progress.get("loneliness_score") is not None:
                            # Convert loneliness score to percentage (10 = worst, 0 = best, so reverse it)
                            progress_percentage = max(0, (10 - latest_progress["loneliness_score"]) * 10)
                        elif latest_progress.get("social_engagement_score") is not None:
                            # Social engagement score (0-10, higher is better)
                            progress_percentage = latest_progress["social_engagement_score"] * 10
                    
                    # Calculate days active
                    created_date = agent.get("created_at", datetime.utcnow())
                    days_active = (datetime.utcnow() - created_date).days
                    
                    # Calculate days until due
                    days_until_due = None
                    if goal.get("due_date"):
                        days_until_due = (goal["due_date"] - datetime.utcnow()).days
                    
                    # Calculate mood average from mood_trend (mood field and stress_level)
                    mood_average = None
                    if mood_trend:
                        recent_moods = [
                            m.get("stress_level", 5) for m in mood_trend 
                            if m.get("date") and m["date"] >= start_date and m.get("stress_level")
                        ]
                        if recent_moods:
                            mood_average = sum(recent_moods) / len(recent_moods)
                    
                    # Last check-in - use 'date' field
                    last_check_in = None
                    if check_ins:
                        last_check_in = max(check_ins, key=lambda x: x.get("date", datetime.min)).get("date")
                    
                    # Count status
                    if goal.get("status") == "active":
                        active_goals += 1
                    elif goal.get("status") == "completed":
                        completed_goals += 1
                    
                    goal_metric = GoalMetricSchema(
                        goal_id=goal.get("goal_id", ""),
                        title=goal.get("title", ""),
                        description=goal.get("description", ""),
                        due_date=goal.get("due_date"),
                        status=goal.get("status", "active"),
                        streak=goal.get("streak", 0),
                        max_streak=goal.get("max_streak", 0),
                        check_ins_count=len(recent_check_ins),
                        progress_percentage=progress_percentage,
                        days_active=days_active,
                        days_until_due=days_until_due,
                        mood_average=mood_average,
                        last_check_in=last_check_in
                    )
                    goal_metrics.append(goal_metric)
                
                agent_summary = AgentGoalSummarySchema(
                    agent_type=agent_type,
                    agent_id=agent.get("id", ""),
                    user_profile_id=agent.get("user_profile_id", ""),
                    total_goals=len(goals),
                    active_goals=active_goals,
                    completed_goals=completed_goals,
                    goals=goal_metrics,
                    last_interaction=agent.get("last_interaction"),
                    created_at=agent.get("created_at", datetime.utcnow())
                )
                agent_summaries.append(agent_summary)
                
                total_goals += len(goals)
                total_active += active_goals
                total_completed += completed_goals
            
            # Create summary statistics
            summary = {
                "total_agents": len(agent_summaries),
                "total_goals": total_goals,
                "active_goals": total_active,
                "completed_goals": total_completed,
                "completion_rate": (total_completed / total_goals * 100) if total_goals > 0 else 0,
                "average_goals_per_agent": total_goals / len(agent_summaries) if agent_summaries else 0,
                "timeframe_summary": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "days": days
                }
            }
            
            return AgentMetricsResponseSchema(
                individual_id=individual_id,
                agent_type=agent_type,
                timeframe=timeframe,
                agents=agent_summaries,
                summary=summary
            )
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch agent metrics: {str(e)}")

    async def get_goal_progress_data(
        self, 
        individual_id: str, 
        agent_type: str, 
        goal_id: str,
        timeframe: str = "30d"
    ) -> GoalProgressDataSchema:
        """Get detailed progress data for a specific goal for charting"""
        try:
            if agent_type not in self.agent_collections:
                raise HTTPException(status_code=400, detail=f"Invalid agent type: {agent_type}")
            
            collection = self.agent_collections[agent_type]
            goal_field = self.goal_fields[agent_type]
            
            # Find the agent with this goal
            agent = collection.find_one({
                f"{goal_field}.goal_id": goal_id
            })
            
            if not agent:
                raise HTTPException(status_code=404, detail="Goal not found")
            
            # Find the specific goal
            goals = agent.get(goal_field, [])
            goal = next((g for g in goals if g.get("goal_id") == goal_id), None)
            
            if not goal:
                raise HTTPException(status_code=404, detail="Goal not found")
            
            # Calculate date range
            end_date = datetime.utcnow()
            timeframe_days = {"7d": 7, "14d": 14, "30d": 30, "90d": 90}
            days = timeframe_days.get(timeframe, 30)
            start_date = end_date - timedelta(days=days)
            
            # Process progress data for charts - using 'date' field
            progress_tracking = goal.get("progress_tracking", [])
            progress_data = []
            
            for progress in progress_tracking:
                if progress.get("date") and progress["date"] >= start_date:
                    # Calculate progress percentage from loneliness/social engagement scores
                    progress_value = 0
                    if progress.get("loneliness_score") is not None:
                        progress_value = max(0, (10 - progress["loneliness_score"]) * 10)
                    elif progress.get("social_engagement_score") is not None:
                        progress_value = progress["social_engagement_score"] * 10
                    
                    progress_data.append({
                        "date": progress["date"],
                        "progress": progress_value,
                        "loneliness_score": progress.get("loneliness_score"),
                        "social_engagement_score": progress.get("social_engagement_score"),
                        "notes": progress.get("notes", ""),
                        "affirmation": progress.get("affirmation", ""),
                        "emotional_trend": progress.get("emotional_trend", "")
                    })
            
            # Process check-in frequency - using 'date' field
            check_ins = goal.get("check_ins", [])
            check_in_frequency = {}
            
            for check_in in check_ins:
                if check_in.get("date") and check_in["date"] >= start_date:
                    date_key = check_in["date"].strftime("%Y-%m-%d")
                    if check_in.get("completed", True):  # Only count completed check-ins
                        check_in_frequency[date_key] = check_in_frequency.get(date_key, 0) + 1
            
            # Process mood trend - using 'date' field
            mood_trend = goal.get("mood_trend", [])
            mood_data = []
            
            for mood in mood_trend:
                if mood.get("date") and mood["date"] >= start_date:
                    mood_data.append({
                        "date": mood["date"],
                        "mood": mood.get("mood", ""),
                        "stress_level": mood.get("stress_level", 5),
                        "notes": mood.get("notes", "")
                    })
            
            # Calculate streak history
            streak_history = []
            current_streak = goal.get("streak", 0)
            max_streak = goal.get("max_streak", 0)
            
            # Generate streak progression data (simplified)
            for i in range(min(days, 30)):  # Last 30 data points max
                date = end_date - timedelta(days=i)
                # This is a simplified calculation - you might want to store actual streak history
                streak_value = max(0, current_streak - i) if i < current_streak else 0
                streak_history.append({
                    "date": date,
                    "streak": streak_value
                })
            
            return GoalProgressDataSchema(
                goal_id=goal_id,
                title=goal.get("title", ""),
                progress_data=sorted(progress_data, key=lambda x: x["date"]),
                check_in_frequency=check_in_frequency,
                mood_trend=sorted(mood_data, key=lambda x: x["date"]),
                streak_history=sorted(streak_history, key=lambda x: x["date"])
            )
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch goal progress data: {str(e)}")

    async def get_agent_analytics_summary(self, individual_id: str, timeframe: str = "30d") -> Dict[str, Any]:
        """Get summary analytics across all agent types"""
        try:
            summary = {
                "timeframe": timeframe,
                "agent_types": {},
                "totals": {
                    "total_agents": 0,
                    "total_goals": 0,
                    "active_goals": 0,
                    "completed_goals": 0,
                    "total_check_ins": 0
                }
            }
            
            for agent_type in self.agent_collections.keys():
                try:
                    metrics = await self.get_agent_metrics(individual_id, agent_type, timeframe)
                    
                    summary["agent_types"][agent_type] = {
                        "agents_count": len(metrics.agents),
                        "total_goals": metrics.summary["total_goals"],
                        "active_goals": metrics.summary["active_goals"],
                        "completed_goals": metrics.summary["completed_goals"],
                        "completion_rate": metrics.summary["completion_rate"]
                    }
                    
                    # Add to totals
                    summary["totals"]["total_agents"] += len(metrics.agents)
                    summary["totals"]["total_goals"] += metrics.summary["total_goals"]
                    summary["totals"]["active_goals"] += metrics.summary["active_goals"]
                    summary["totals"]["completed_goals"] += metrics.summary["completed_goals"]
                    
                except Exception:
                    # If an agent type has no data, skip it
                    continue
            
            # Calculate overall completion rate
            if summary["totals"]["total_goals"] > 0:
                summary["totals"]["completion_rate"] = (
                    summary["totals"]["completed_goals"] / summary["totals"]["total_goals"] * 100
                )
            else:
                summary["totals"]["completion_rate"] = 0
            
            return summary
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch analytics summary: {str(e)}")
