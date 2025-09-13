"""
Minimal working accountability agent for testing
"""

import logging
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime

# Import common models
from common.models import AgentResult

logger = logging.getLogger(__name__)

async def process_message(
    text: str,
    conversation_id: str,
    user_profile_id: str,
    agent_instance_id: str,
    checkpoint: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    individual_id: Optional[str] = None,
) -> AgentResult:
    """Accountability agent flow with no creation logic; only updates allowed fields."""
    try:
        # Import database manager and LLM service
        from .database_manager import AccountabilityDatabaseManager
        from .llm_service import AccountabilityLLMService
        
        # Initialize database manager (no creation)
        db_manager = AccountabilityDatabaseManager()
        await db_manager.initialize()

        # Load personalization profile (read-only)
        user_profile = await db_manager.get_user_profile(user_profile_id)

        # Load accountability agent doc and pick active goal
        agent_doc = await db_manager.get_accountability_agent_doc(user_profile_id)
        if not agent_doc or not agent_doc.get("accountability_goals"):
            reply = (
                "I’m ready to support your accountability journey. "
                "Please create a goal first from your profile to get started."
            )
            return AgentResult(
                agent_name="Accountability Buddy",
                status="no_goal",
                result_payload={"reply": reply, "intent": "no_goal"},
                message_to_user=reply,
                action_required=False,
                timestamp=datetime.utcnow()
            )

        # Choose goal: prefer a goal whose goal_id matches agent_instance_id (for client convenience),
        # otherwise select the active goal or last one
        goals = agent_doc.get("accountability_goals", [])
        active_goal = next((g for g in goals if g.get("goal_id") == agent_instance_id), None)
        if not active_goal:
            active_goal = db_manager._select_active_goal(agent_doc)
        goal_id = active_goal.get("goal_id") if active_goal else None
        if not goal_id:
            reply = (
                "I couldn’t find an active goal. Please set a goal from your profile to continue."
            )
            return AgentResult(
                agent_name="Accountability Buddy",
                status="no_goal",
                result_payload={"reply": reply, "intent": "no_goal"},
                message_to_user=reply,
                action_required=False,
                timestamp=datetime.utcnow()
            )
        
        # Initialize LLM service
        llm_service = AccountabilityLLMService()
        await llm_service.initialize()
        
        # Analyze intent
        intent_result = await llm_service.analyze_intent(text, context or {})
        intent = intent_result.get("intent", "general_conversation")
        
        # Determine checkpoint (fallback to GREETING)
        current_checkpoint = checkpoint or "GREETING"

        # Checklist progress detection (read-only; no DB fields added)
        try:
            from conversionalEngine.specialists.checklist.agent import track_checkpoint_progress
            # Convert context to expected list format if needed
            context_list: List[Dict[str, str]] = []
            if isinstance(context, list):
                context_list = context  # assume already in correct shape
            elif isinstance(context, dict):
                context_list = [{"key": k, "value": str(v)} for k, v in context.items()]
            checklist = await track_checkpoint_progress(text, None, context_list)
        except Exception:
            checklist = {"checkpoint_complete": False, "progress_percentage": 0.0, "confidence": 0.0}
        
        # Generate appropriate response based on intent
        checkin_completed = False
        
        if intent == "goal_creation":
            # Do not create here; direct user to create via profile endpoint
            reply = (
                "That sounds like a great goal! Please add it from your profile "
                "(Goals > Accountability) and I’ll start tracking right away."
            )
            current_checkpoint = "GOAL_CREATION"
                
        elif intent == "daily_checkin":
            reply = "Great! Let's check in on your progress. How did you do today? Rate yourself 1-10! 📊"
            current_checkpoint = "DAILY_CHECKIN"
            
        elif intent == "rating_response":
            rating = intent_result.get("extracted_data", {}).get("rating", 5)
            reply = await llm_service.generate_checkin_response({"rating": rating, "overall_score": rating})
            checkin_completed = True
            current_checkpoint = "RATING_RESPONSE"
            
        elif intent == "motivation_request":
            reply = await llm_service.generate_motivation_message({"user_text": text})
            current_checkpoint = "MOTIVATION_REQUEST"
            
        else:
            reply = "Hi there! I'm your Accountability Buddy, here to support your goals and celebrate your progress! 🎯"
            current_checkpoint = "GENERAL_CONVERSATION"
        
        # Compute and persist allowed updates on the selected goal only
        # Daily check-in example: append to check_ins and adjust streaks
        # Determine daily streak changes BEFORE appending today's check-in
        # Build set of existing active days
        from datetime import timezone
        today_utc = datetime.utcnow().date()
        existing_dates = []
        for ci in (active_goal.get("check_ins") or []):
            try:
                # handle both datetime and string
                d = ci.get("date")
                if isinstance(d, str):
                    d = datetime.fromisoformat(d.replace("Z", "+00:00")).astimezone(timezone.utc)
                if isinstance(d, datetime):
                    existing_dates.append(d.date())
            except Exception:
                continue
        has_today_entry = today_utc in existing_dates
        last_active_date = max(existing_dates) if existing_dates else None
        old_streak = int(active_goal.get("streak") or 0)
        old_max = int(active_goal.get("max_streak") or 0)

        if intent in ("daily_checkin", "rating_response", "general_conversation", "progress_review"):
            # Append checkin
            checkin_doc = {
                "date": datetime.utcnow(),
                "response": str(text),
                "completed": True,
                "notes": text[:200],
            }
            await db_manager.append_checkin(user_profile_id, goal_id, checkin_doc)

            # Daily streak logic: increment once per calendar day, reset if gap > 1 day
            if has_today_entry:
                current_streak = old_streak
                max_streak = old_max
            else:
                if last_active_date is None:
                    current_streak = 1
                    max_streak = max(old_max, current_streak)
                else:
                    days_diff = (today_utc - last_active_date).days
                    if days_diff == 1:
                        current_streak = old_streak + 1
                        max_streak = max(old_max, current_streak)
                    elif days_diff > 1:
                        # Inactivity day occurred → reset max to 0 and streak to 1
                        current_streak = 1
                        max_streak = 0
                    else:
                        # same-day check-in just recorded
                        current_streak = old_streak
                        max_streak = old_max
            await db_manager.set_streaks(user_profile_id, goal_id, current_streak, max_streak)

        # Helper: infer mood + stress and trend/engagement without LLM (fallbacks)
        def _infer_mood_and_stress(user_text: str, extracted: Dict[str, Any]) -> Dict[str, Any]:
            positive_words = ["happy", "joy", "joyful", "excited", "glad", "great", "good", "calm", "relaxed", "content"]
            negative_words = ["sad", "anxious", "anxiety", "stressed", "stress", "angry", "upset", "depressed", "worried"]
            mood = extracted.get("mood")
            if mood:
                mv = str(mood).lower()
            else:
                ltext = (user_text or "").lower()
                mv = None
                if any(w in ltext for w in positive_words):
                    mv = "happy"
                elif any(w in ltext for w in negative_words):
                    mv = "stressed" if "stress" in ltext or "stressed" in ltext else "sad"
                else:
                    mv = "neutral"

            # stress based on mood or rating
            rating_val_local = extracted.get("rating")
            if mv in ["happy", "joyful", "excited", "calm", "relaxed", "content", "good", "great"]:
                stress = 2
            elif mv in ["sad", "depressed", "anxious", "worried", "stressed", "angry", "upset"]:
                stress = 8
            elif isinstance(rating_val_local, (int, float)):
                # invert rating into stress (higher rating → lower stress)
                stress = max(1, min(10, int(round(11 - float(rating_val_local)))))
            else:
                stress = 5

            return {"mood": mv, "stress_level": stress}

        extracted = intent_result.get("extracted_data", {}) or {}
        inferred = _infer_mood_and_stress(text, extracted)

        # Always append to progress_tracking (loneliness_score must remain null for accountability)
        # Derive social engagement (rough heuristic from rating or sentiment words)
        if isinstance(extracted.get("rating"), (int, float)):
            social_score = max(1.0, min(10.0, float(extracted.get("rating"))))
        else:
            social_score = 7.0 if inferred["mood"] in ["happy", "joyful", "excited", "good", "great", "content"] else 4.0 if inferred["mood"] in ["sad", "depressed", "anxious", "worried", "stressed", "angry", "upset"] else 5.0

        # Emotional trend heuristic
        if social_score >= 7.0:
            trend = "improving"
        elif social_score <= 4.0:
            trend = "declining"
        else:
            trend = "stable"

        progress_entry = {
            "date": datetime.utcnow(),
            "loneliness_score": None,  # explicitly keep null for accountability agent
            "social_engagement_score": float(social_score),
            "affirmation": "Keep going — you’re doing great.",
            "emotional_trend": trend,
            "notes": text[:300]
        }
        await db_manager.append_progress_tracking(user_profile_id, goal_id, progress_entry)

        # Always append to mood_trend (fallback to neutral if mood not extracted)
        mood_value = str(inferred["mood"])[:64]
        stress_level = int(inferred["stress_level"])
        mood_log = {"date": datetime.utcnow(), "mood": mood_value, "stress_level": stress_level, "notes": text[:120]}
        await db_manager.append_mood_trend(user_profile_id, goal_id, mood_log)
        
        return AgentResult(
            agent_name="Accountability Buddy",
            status="success",
            result_payload={"reply": reply, "intent": intent, "checkpoint": current_checkpoint},
            message_to_user=reply,
            action_required=False,
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"❌ Error in minimal accountability agent: {e}")
        return AgentResult(
            agent_name="Accountability Buddy",
            status="error",
            result_payload={"error": str(e)},
            message_to_user="I'm having some trouble right now, but I'm still here to support your goals!",
            action_required=False,
            timestamp=datetime.utcnow()
        )
