"""
Therapy agent flow mirroring accountability agent behavior:
- No creation here (creation via user profile endpoint)
- Reads therapy_agents, selects goal by goal_id==agent_instance_id else active/last
- Updates only: check_ins, streak, max_streak, progress_tracking, mood_trend
- Fills non-null fields each request; daily streak logic (once per day)
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

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
    try:
        from .database_manager import TherapyDatabaseManager
        from .llm_service import TherapyLLMService

        db_manager = TherapyDatabaseManager()
        await db_manager.initialize()

        user_profile = await db_manager.get_user_profile(user_profile_id)

        agent_doc = await db_manager.get_therapy_agent_doc(user_profile_id)
        if not agent_doc or not agent_doc.get("therapy_goals"):
            reply = (
                "I’m here to support your therapy check-ins. Please create a therapy goal "
                "from your profile to begin."
            )
            return AgentResult(
                agent_name="Therapy Check-In",
                status="no_goal",
                result_payload={"reply": reply, "intent": "no_goal"},
                message_to_user=reply,
                action_required=False,
                timestamp=datetime.utcnow()
            )

        goals = agent_doc.get("therapy_goals", [])
        active_goal = next((g for g in goals if g.get("goal_id") == agent_instance_id), None)
        if not active_goal:
            active_goal = db_manager._select_active_goal(agent_doc)
        goal_id = active_goal.get("goal_id") if active_goal else None
        if not goal_id:
            reply = (
                "I couldn’t find an active therapy goal. Please add one from your profile to continue."
            )
            return AgentResult(
                agent_name="Therapy Check-In",
                status="no_goal",
                result_payload={"reply": reply, "intent": "no_goal"},
                message_to_user=reply,
                action_required=False,
                timestamp=datetime.utcnow()
            )

        current_checkpoint = checkpoint or "GREETING"

        # Initialize LLM service (optional, used for replies only)
        llm_service = TherapyLLMService()
        await llm_service.initialize()

        # Analyze intent (local heuristic to avoid dependency on LLM API)
        import re
        def _simple_intent(user_text: str) -> Dict[str, Any]:
            lower = (user_text or "").lower()
            # rating 1-10
            m = re.search(r"\b(10|[1-9])\b", lower)
            if m:
                try:
                    return {"intent": "rating_response", "extracted_data": {"rating": int(m.group(1))}}
                except Exception:
                    pass
            if any(w in lower for w in ["check in", "check-in", "today", "mood", "feeling"]):
                return {"intent": "daily_checkin", "extracted_data": {}}
            if any(w in lower for w in ["progress", "summary", "insight", "stats"]):
                return {"intent": "progress_review", "extracted_data": {}}
            return {"intent": "general_conversation", "extracted_data": {}}

        intent_result = _simple_intent(text)
        intent = intent_result.get("intent", "general_conversation")

        # Checklist (reuse accountability checklist util if needed)
        try:
            from conversionalEngine.specialists.checklist.agent import track_checkpoint_progress
            context_list: List[Dict[str, str]] = []
            if isinstance(context, list):
                context_list = context
            elif isinstance(context, dict):
                context_list = [{"key": k, "value": str(v)} for k, v in context.items()]
            checklist = await track_checkpoint_progress(text, None, context_list)
        except Exception:
            checklist = {"checkpoint_complete": False, "progress_percentage": 0.0, "confidence": 0.0}

        # Daily streak logic
        today_utc = datetime.utcnow().date()
        existing_dates = []
        for ci in (active_goal.get("check_ins") or []):
            try:
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

        # Append check-in for therapy each request
        checkin_doc = {
            "date": datetime.utcnow(),
            "response": str(text),
            "completed": True,
            "notes": text[:200],
        }
        success_ci = await db_manager.append_checkin(user_profile_id, goal_id, checkin_doc)

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
                    current_streak = 1
                    max_streak = 0
                else:
                    current_streak = old_streak
                    max_streak = old_max
        success_streak = await db_manager.set_streaks(user_profile_id, goal_id, current_streak, max_streak)

        # Heuristics for progress + mood (therapy specific: keep loneliness_score null here as well)
        extracted = intent_result.get("extracted_data", {}) or {}
        def _infer_mood(user_text: str, extracted_local: Dict[str, Any]) -> str:
            if extracted_local.get("mood"):
                return str(extracted_local.get("mood")).lower()
            t = (user_text or "").lower()
            if any(w in t for w in ["happy", "content", "calm", "relaxed", "better"]):
                return "calm"
            if any(w in t for w in ["sad", "down", "anxious", "stressed", "angry", "hopeless"]):
                return "distressed"
            return "neutral"

        mood_value = _infer_mood(text, extracted)
        # stress: derive from keywords or rating
        if mood_value in ["calm", "neutral"]:
            stress_level = 3 if mood_value == "calm" else 5
        else:
            stress_level = 8
        if isinstance(extracted.get("rating"), (int, float)):
            stress_level = max(1, min(10, int(round(11 - float(extracted.get("rating"))))))

        # progress_tracking
        social_score = 6.0 if mood_value == "calm" else 4.0 if mood_value == "distressed" else 5.0
        trend = "improving" if social_score >= 7.0 else "declining" if social_score <= 4.0 else "stable"
        progress_entry = {
            "date": datetime.utcnow(),
            "loneliness_score": None,
            "social_engagement_score": float(social_score),
            "affirmation": "You’re doing the right thing by sharing. I’m here with you.",
            "emotional_trend": trend,
            "notes": text[:300]
        }
        success_prog = await db_manager.append_progress_tracking(user_profile_id, goal_id, progress_entry)

        # mood_trend
        mood_log = {
            "date": datetime.utcnow(),
            "mood": mood_value,
            "stress_level": stress_level,
            "notes": text[:120]
        }
        success_mood = await db_manager.append_mood_trend(user_profile_id, goal_id, mood_log)

        # Final reply (fallback safe)
        reply = "Thank you for checking in. I’m here to listen and support you."

        logger.info(f"Therapy updates: checkin={success_ci}, streak={success_streak}, progress={success_prog}, mood={success_mood}")
        return AgentResult(
            agent_name="Therapy Check-In",
            status="success",
            result_payload={"reply": reply, "intent": intent, "checkpoint": current_checkpoint},
            message_to_user=reply,
            action_required=False,
            timestamp=datetime.utcnow()
        )

    except Exception as e:
        logger.error(f"❌ Error in minimal therapy agent: {e}")
        return AgentResult(
            agent_name="Therapy Check-In",
            status="error",
            result_payload={"error": str(e)},
            message_to_user="I’m having trouble right now, but I’m here for you. Please try again.",
            action_required=False,
            timestamp=datetime.utcnow()
        )


