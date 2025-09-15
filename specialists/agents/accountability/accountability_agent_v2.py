"""
Therapy-like Accountability Agent
Mirrors the therapy agent architecture (data_manager, background scheduling, streaming),
but with accountability-specific behavior and prompts.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Dict, Optional

from .data_manager_v2 import AccountabilityDataManagerV2
from .gemini_streaming import get_streaming_client

logger = logging.getLogger(__name__)


class AccountabilityAgentV2:
    def __init__(self):
        # Initialize Redis and MongoDB clients like loneliness agent
        try:
            from memory.redis_client import RedisMemory
            from memory.mongo_client import MongoMemory
            self.redis_client = RedisMemory()
            self.mongo_client = MongoMemory()
        except ImportError:
            # Use fallback clients if memory clients not available
            self.redis_client = None
            self.mongo_client = None
        
        # Initialize data manager with clients like loneliness agent
        self.data_manager = AccountabilityDataManagerV2(self.redis_client, self.mongo_client)
        self.streaming_client = get_streaming_client()
        self._session_cache: Dict[str, Dict[str, Any]] = {}
        self._profile_cache: Dict[str, Any] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize all connections and clients - mirrors loneliness agent"""
        if self._initialized:
            return
            
        try:
            # Initialize connections in parallel for faster startup like loneliness agent
            if self.redis_client:
                redis_task = asyncio.create_task(self.redis_client.check_connection())
            if self.mongo_client:
                mongo_init_task = asyncio.create_task(self.mongo_client.initialize())
            
            # Wait for connections with timeout
            if self.redis_client and self.mongo_client:
                await asyncio.wait_for(
                    asyncio.gather(redis_task, mongo_init_task, return_exceptions=True),
                    timeout=5.0
                )
            
            self._initialized = True
            logger.info("AccountabilityAgentV2 initialized successfully")
            
        except asyncio.TimeoutError:
            logger.warning("AccountabilityAgentV2 initialization timeout - continuing with fallbacks")
            self._initialized = True
        except Exception as e:
            logger.error(f"AccountabilityAgentV2 init error: {e} - continuing with fallbacks")
            self._initialized = True

    async def get_cached_data(self, user_profile_id: str, agent_instance_id: str):
        profile = await self.data_manager.get_user_profile(user_profile_id)
        agent_data = await self.data_manager.get_accountability_agent_data(user_profile_id, agent_instance_id)
        # Convert Pydantic objects to dictionaries for compatibility
        profile_dict = profile.model_dump() if hasattr(profile, 'model_dump') else profile
        agent_dict = agent_data.model_dump() if hasattr(agent_data, 'model_dump') else agent_data
        return profile_dict, agent_dict

    async def get_session_state_fast(self, conversation_id: str, user_profile_id: str) -> Dict[str, Any]:
        return await self.data_manager.get_session_state(conversation_id, user_profile_id)

    async def build_prompt(self, user_query: str, user_profile: Dict[str, Any], session_state: Dict[str, Any]) -> str:
        name = user_profile.get("name", "Friend") if isinstance(user_profile, dict) else getattr(user_profile, "name", "Friend")
        interests = user_profile.get("interests", []) if isinstance(user_profile, dict) else getattr(user_profile, "interests", [])
        interest_str = ", ".join(interests[:3]) if interests else "your goals"
        mood = session_state.get("current_mood", "neutral")
        history_turns = session_state.get("conversation_turns", [])
        last_turn = history_turns[-1] if history_turns else {}
        last_agent = last_turn.get("agent", "") if isinstance(last_turn, dict) else ""
        prompt = (
            f"You are an Accountability Buddy. Be encouraging, practical, and brief.\n"
            f"User: {name}. Interests: {interest_str}. Current mood: {mood}.\n"
            f"Context: last_agent='{last_agent}'.\n"
            f"User says: {user_query}\n"
            f"Respond with 1-3 short sentences, include one concrete next step if appropriate."
        )
        return prompt

    async def process_message(self,
        text: str,
        conversation_id: str,
        user_profile_id: str,
        agent_instance_id: str,
        user_id: str = "",
        checkpoint: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        individual_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self._initialized:
            await self.initialize()
        try:
            user_profile, agent_data = await self.get_cached_data(user_profile_id, agent_instance_id)
            session_state = await self.get_session_state_fast(conversation_id, user_profile_id)
        except Exception as e:
            logger.warning(f"Accountability data fetch error: {e}, using defaults")
            user_profile = {"name": "Friend", "interests": []}
            agent_data = {"accountability_goals": []}
            session_state = {"current_mood": "neutral", "conversation_turns": []}

        profile_dict = user_profile.model_dump() if hasattr(user_profile, 'model_dump') else user_profile
        prompt = await self.build_prompt(text, profile_dict, session_state)

        try:
            resp = await self.streaming_client.generate_content(prompt)
            reply = getattr(resp, "text", "I'm here to support your goals. What feels like the next step?")
        except Exception as e:
            logger.warning(f"LLM generation failed: {e}")
            reply = "I'm here to support your goals. What feels like the next step?"

        await self.data_manager.update_session_state(conversation_id, user_profile_id, {
            "last_reply": reply,
            "conversation_turns": (session_state.get("conversation_turns") or []) + [{"user": text, "agent": reply}],
        })

        # Persist a lightweight log
        try:
            await self.data_manager.log_conversation(user_profile_id, agent_instance_id, conversation_id, text, reply)
        except Exception:
            pass

        # Persist mood/progress entries similarly to therapy agent
        try:
            # Add a check-in entry and streak update
            await self.data_manager.add_check_in(user_profile_id, agent_instance_id, text)
            # simple heuristics
            rating = 7 if any(w in (text or "").lower() for w in ["great","good","progress","done"]) else 5
            feelings = ["motivated"] if rating >= 7 else ["neutral"]
            await self.data_manager.add_mood_log(user_profile_id, agent_instance_id, rating, feelings, text, risk_level=0)
            # progress
            engagement_score = 7.0 if rating >= 7 else 5.0
            await self.data_manager.update_progress(user_profile_id, agent_instance_id, float(rating), engagement_score, f"Conversation completed")
        except Exception:
            pass

        return {
            "response": reply,
            "checkpoint_status": "completed",
            "requires_human": False,
            "agent_specific_data": {"goals_count": len((agent_data or {}).get("accountability_goals", []))},
        }

    async def stream_accountability_response(self,
        text: str,
        conversation_id: str,
        checkpoint: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        individual_id: Optional[str] = None,
        user_profile_id: str = "",
        agent_instance_id: str = "",
        user_id: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        yield {"type": "start", "conversation_id": conversation_id, "timestamp": time.time()}
        if not self._initialized:
            await self.initialize()
        try:
            user_profile, agent_data = await self.get_cached_data(user_profile_id, agent_instance_id)
            session_state = await self.get_session_state_fast(conversation_id, user_profile_id)
        except Exception:
            user_profile = {"name": "Friend", "interests": []}
            agent_data = {"accountability_goals": []}
            session_state = {"current_mood": "neutral", "conversation_turns": []}
        profile_dict = user_profile.model_dump() if hasattr(user_profile, 'model_dump') else user_profile
        prompt = await self.build_prompt(text, profile_dict, session_state)
        full = ""
        async for chunk in self.streaming_client.stream_generate_content(prompt, max_tokens=200, temperature=0.7, chunk_size=2):
            chunk["conversation_id"] = conversation_id
            yield chunk
            if chunk.get("type") == "content":
                full += chunk.get("data", "")
            elif chunk.get("type") == "done":
                full = chunk.get("data", full)
                break
        yield {"type": "complete", "conversation_id": conversation_id, "response_length": len(full), "timestamp": time.time()}
        await self.data_manager.update_session_state(conversation_id, user_profile_id, {
            "last_reply": full or "",
            "conversation_turns": (session_state.get("conversation_turns") or []) + [{"user": text, "agent": full}],
        })
        try:
            await self.data_manager.log_conversation(user_profile_id, agent_instance_id, conversation_id, text, full or "")
        except Exception:
            pass
        try:
            await self.data_manager.add_check_in(user_profile_id, agent_instance_id, text)
            rating = 7 if any(w in (text or "").lower() for w in ["great","good","progress","done"]) else 5
            feelings = ["motivated"] if rating >= 7 else ["neutral"]
            await self.data_manager.add_mood_log(user_profile_id, agent_instance_id, rating, feelings, text, risk_level=0)
            engagement_score = 7.0 if rating >= 7 else 5.0
            await self.data_manager.update_progress(user_profile_id, agent_instance_id, float(rating), engagement_score, f"Streaming conversation completed")
        except Exception:
            pass


accountability_agent_v2 = AccountabilityAgentV2()