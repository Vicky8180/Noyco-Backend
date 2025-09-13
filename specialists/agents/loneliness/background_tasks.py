"""
Background Task Manager for Loneliness Companion Agent
Handles async processing of mood analysis, progress tracking, and data persistence.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor
import json

logger = logging.getLogger(__name__)

class BackgroundTaskManager:
    """Optimized background task manager for ultra-low latency processing"""
    
    def __init__(self, max_workers: int = 4):  # Reduced workers for better resource management
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._task_queue = asyncio.Queue(maxsize=100)  # Prevent memory overload
        self._mood_cache: Dict[str, str] = {}  # Cache mood analysis results
        
    async def schedule_mood_analysis(self, user_id: str, text: str, gemini_client) -> str:
        """Ultra-fast mood analysis with caching and keyword-only analysis - NO LLM CALLS"""
        # Create cache key
        text_hash = hash(text)
        cache_key = f"{user_id}_{text_hash}"
        
        # Check cache first
        if cache_key in self._mood_cache:
            return self._mood_cache[cache_key]
        
        # Use ONLY keyword analysis - NO LLM CALLS TO CONSERVE QUOTA
        mood_analyzer = MoodAnalyzer()
        quick_mood = mood_analyzer.quick_mood_analysis(text)
        
        # Cache the result
        self._mood_cache[cache_key] = quick_mood
        
        # NO BACKGROUND LLM TASKS TO SAVE QUOTA
        logger.debug(f"Keyword-only mood analysis for {user_id}: {quick_mood}")
        
        return quick_mood
    
    async def _analyze_mood_background(self, text: str, gemini_client, cache_key: str = None) -> str:
        """Background mood analysis - DISABLED TO SAVE QUOTA, USE KEYWORDS ONLY"""
        try:
            # NO GEMINI CALLS - Use keyword analysis only
            mood_analyzer = MoodAnalyzer()
            mood = mood_analyzer.quick_mood_analysis(text)
            
            # Cache result if key provided
            if cache_key and hasattr(self, '_mood_cache'):
                self._mood_cache[cache_key] = mood
            
            logger.debug(f"Background keyword mood analysis: {mood}")
            return mood
            
        except Exception as e:
            logger.warning(f"Background mood analysis failed: {e}")
            return "neutral"
    
    async def schedule_progress_update(
        self, 
        user_profile_id: str,
        agent_instance_id: str,
        loneliness_score: float, 
        engagement_score: float, 
        notes: str,
        data_manager
    ):
        """Schedule progress update in background"""
        task = asyncio.create_task(
            self._update_progress_background(
                user_profile_id, agent_instance_id, loneliness_score, engagement_score, notes, data_manager
            )
        )
        # Don't wait for completion
        return task
    
    async def _update_progress_background(
        self, 
        user_profile_id: str,
        agent_instance_id: str,
        loneliness_score: float, 
        engagement_score: float, 
        notes: str,
        data_manager
    ):
        """Background progress update"""
        try:
            await data_manager.update_progress(user_profile_id, agent_instance_id, loneliness_score, engagement_score, notes)
            logger.debug(f"Background progress update complete for {user_profile_id}:{agent_instance_id}")
        except Exception as e:
            logger.error(f"Background progress update failed for {user_profile_id}:{agent_instance_id}: {e}")
    
    async def schedule_data_sync(self, user_profile_id: str, agent_instance_id: str, data_manager):
        """Schedule data synchronization to DB"""
        task = asyncio.create_task(self._sync_data_background(user_profile_id, agent_instance_id, data_manager))
        return task
    
    async def _sync_data_background(self, user_profile_id: str, agent_instance_id: str, data_manager):
        """Background data sync to MongoDB"""
        try:
            await data_manager.sync_agent_data_to_db(user_profile_id, agent_instance_id)
            logger.debug(f"Background data sync complete for {user_profile_id}:{agent_instance_id}")
        except Exception as e:
            logger.error(f"Background data sync failed for {user_profile_id}:{agent_instance_id}: {e}")
    
    def schedule_daily_checkin_update(self, user_profile_id: str, agent_instance_id: str, user_query: str, mood: str, data_manager):
        """Schedule daily check-in update"""
        self.executor.submit(self._update_daily_checkin_sync, user_profile_id, agent_instance_id, user_query, mood, data_manager)
    
    def _update_daily_checkin_sync(self, user_profile_id: str, agent_instance_id: str, user_query: str, mood: str, data_manager):
        """Synchronous daily check-in update for thread executor"""
        try:
            # Run the async method in the thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(data_manager.add_check_in(user_profile_id, agent_instance_id, user_query))
            loop.close()
            logger.debug(f"Daily check-in update complete for {user_profile_id}:{agent_instance_id}")
        except Exception as e:
            logger.error(f"Daily check-in update failed for {user_profile_id}:{agent_instance_id}: {e}")
    
    def cleanup(self):
        """Clean up resources"""
        # Cancel running tasks
        for task in self._running_tasks.values():
            if not task.done():
                task.cancel()
        
        # Shutdown executor
        self.executor.shutdown(wait=False)


class MoodAnalyzer:
    """Lightweight mood analysis with keyword-based fallback"""
    
    def __init__(self):
        self.mood_keywords = {
            "happy": ["happy", "joy", "excited", "great", "wonderful", "amazing", "good", "smile", "laugh"],
            "sad": ["sad", "down", "depressed", "blue", "upset", "crying", "tears", "hurt", "pain"],
            "anxious": ["anxious", "worried", "nervous", "stress", "scared", "fear", "panic", "tense"],
            "lonely": ["lonely", "alone", "isolated", "empty", "disconnected", "nobody", "solitary"],
            "frustrated": ["frustrated", "angry", "mad", "annoyed", "irritated", "fed up", "bothered"],
            "neutral": ["okay", "fine", "normal", "usual", "same", "nothing", "regular"]
        }
    
    def quick_mood_analysis(self, text: str) -> str:
        """Quick keyword-based mood analysis for immediate response"""
        text_lower = text.lower()
        mood_scores = {mood: 0 for mood in self.mood_keywords.keys()}
        
        # Count keyword matches
        for mood, keywords in self.mood_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    mood_scores[mood] += 1
        
        # Return mood with highest score, default to neutral
        if max(mood_scores.values()) > 0:
            return max(mood_scores, key=mood_scores.get)
        else:
            return "neutral"
    
    async def enhanced_mood_analysis(self, text: str, gemini_client) -> str:
        """Enhanced mood analysis using keywords only - NO GEMINI CALLS TO SAVE QUOTA"""
        try:
            # Use keyword-based analysis only to save quota
            return self.quick_mood_analysis(text)
            
        except Exception as e:
            logger.error(f"Enhanced mood analysis failed: {e}")
            # Fallback to quick analysis
            return self.quick_mood_analysis(text)


class ProgressTracker:
    """Tracks user progress and engagement metrics"""
    
    @staticmethod
    def calculate_loneliness_score(mood: str, user_query: str, conversation_history: List[Dict] = None) -> float:
        """Calculate loneliness score (0-10, lower is better)"""
        mood_scores = {
            "happy": 2.0,
            "neutral": 5.0,
            "sad": 7.0,
            "anxious": 6.5,
            "lonely": 8.5,
            "frustrated": 6.0
        }
        
        base_score = mood_scores.get(mood, 5.0)
        
        # Adjust based on content
        lonely_keywords = ["alone", "lonely", "isolated", "nobody", "empty", "disconnected", "by myself"]
        positive_keywords = ["good", "better", "happy", "glad", "thankful", "connected", "together"]
        social_keywords = ["friends", "family", "people", "someone", "talked", "meeting", "social"]
        
        query_lower = user_query.lower()
        
        # Increase score for loneliness indicators
        for keyword in lonely_keywords:
            if keyword in query_lower:
                base_score += 0.5
        
        # Decrease score for positive indicators
        for keyword in positive_keywords:
            if keyword in query_lower:
                base_score -= 0.5
        
        # Decrease score for social connection indicators
        for keyword in social_keywords:
            if keyword in query_lower:
                base_score -= 0.3
        
        # Consider conversation history if available
        if conversation_history:
            # Defensive programming: ensure conversation_history items are dictionaries
            safe_history = []
            for turn in conversation_history[-5:]:
                if isinstance(turn, dict):
                    safe_history.append(turn)
                elif isinstance(turn, str):
                    logger.warning(f"Found string in conversation history: {turn[:50]}...")
                    safe_history.append({"mood": "neutral"})  # Convert to dict
                else:
                    logger.warning(f"Found unexpected type in conversation history: {type(turn)}")
                    safe_history.append({"mood": "neutral"})
            
            recent_moods = [turn.get('mood', 'neutral') for turn in safe_history]
            lonely_count = recent_moods.count('lonely')
            if lonely_count >= 3:
                base_score += 1.0  # Persistent loneliness
            elif lonely_count == 0:
                base_score -= 0.5  # No recent loneliness
        
        return max(0.0, min(10.0, base_score))
    
    @staticmethod
    def calculate_engagement_score(user_query: str, agent_response: str, turn_count: int = 1) -> float:
        """Calculate social engagement score (0-10, higher is better)"""
        base_score = 5.0
        
        # Length indicates engagement
        if len(user_query) > 50:
            base_score += 1.0
        if len(user_query) > 100:
            base_score += 1.0
        if len(user_query) > 200:
            base_score += 0.5
            
        # Questions indicate engagement
        question_count = user_query.count("?")
        base_score += min(question_count * 0.5, 2.0)
            
        # Personal sharing indicates engagement
        sharing_keywords = ["i feel", "i think", "my", "today i", "yesterday", "i was", "i am", "i did", "i went"]
        query_lower = user_query.lower()
        
        for keyword in sharing_keywords:
            if keyword in query_lower:
                base_score += 0.5
        
        # Emotional expression indicates engagement
        emotion_words = ["feel", "feeling", "emotion", "think", "believe", "hope", "wish", "want"]
        for word in emotion_words:
            if word in query_lower:
                base_score += 0.3
        
        # Conversation turn bonus (more turns = more engagement)
        if turn_count > 3:
            base_score += min((turn_count - 3) * 0.1, 1.0)
        
        return max(0.0, min(10.0, base_score))
    
    @staticmethod
    def calculate_improvement_trend(progress_entries: List[Dict], days: int = 7) -> Dict[str, Any]:
        """Calculate improvement trend over specified days"""
        if not progress_entries or len(progress_entries) < 2:
            return {"trend": "insufficient_data", "change": 0.0}
        
        # Filter entries to specified time window
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Defensive programming: ensure progress_entries items are dictionaries
        safe_entries = []
        for entry in progress_entries:
            if isinstance(entry, dict):
                safe_entries.append(entry)
            elif isinstance(entry, str):
                logger.warning(f"Found string in progress entries: {entry[:50]}...")
                # Skip string entries as they can't be processed
                continue
            else:
                logger.warning(f"Found unexpected type in progress entries: {type(entry)}")
                continue
        
        recent_entries = [
            entry for entry in safe_entries
            if entry.get('date') and datetime.fromisoformat(entry['date'].replace('Z', '+00:00')) >= cutoff_date
        ]
        
        if len(recent_entries) < 2:
            return {"trend": "insufficient_data", "change": 0.0}
        
        # Calculate trends
        loneliness_scores = [entry.get('loneliness_score') for entry in recent_entries if entry.get('loneliness_score') is not None]
        engagement_scores = [entry.get('social_engagement_score') for entry in recent_entries if entry.get('social_engagement_score') is not None]
        
        result = {"trend": "stable", "change": 0.0, "details": {}}
        
        if loneliness_scores:
            loneliness_change = loneliness_scores[-1] - loneliness_scores[0]
            result["details"]["loneliness_change"] = loneliness_change
            
        if engagement_scores:
            engagement_change = engagement_scores[-1] - engagement_scores[0]
            result["details"]["engagement_change"] = engagement_change
        
        # Determine overall trend (improvement = lower loneliness OR higher engagement)
        total_change = 0.0
        if loneliness_scores:
            total_change -= loneliness_change  # Lower loneliness is better
        if engagement_scores:
            total_change += engagement_change  # Higher engagement is better
            
        result["change"] = total_change
        
        if total_change > 1.0:
            result["trend"] = "improving"
        elif total_change < -1.0:
            result["trend"] = "declining"
        else:
            result["trend"] = "stable"
            
        return result
