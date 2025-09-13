"""
LLM Service for Accountability Buddy Agent
Handles intelligent response generation, intent analysis, and goal-related AI tasks
"""

import logging
import json
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

import google.generativeai as genai
from ..config import get_settings

logger = logging.getLogger(__name__)

class AccountabilityLLMService:
    """LLM service for accountability agent using Gemini"""
    
    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = settings.LLM_ENGINE
        self.model = None
        self.initialized = False
        
    async def initialize(self):
        """Initialize Gemini client"""
        try:
            if not self.api_key:
                logger.warning("⚠️ No Gemini API key provided for accountability LLM service")
                return
                
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
            self.initialized = True
            logger.info("✅ Accountability LLM service initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize accountability LLM service: {e}")
            # Continue without LLM - use fallback responses
    
    async def analyze_intent(self, user_text: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Analyze user intent for accountability actions"""
        try:
            if not self.initialized or not self.model:
                return self._fallback_intent_analysis(user_text)
            
            prompt = f"""
            Analyze this user message for accountability/goal-tracking intent:
            
            User message: "{user_text}"
            Context: {json.dumps(context or {}, indent=2)}
            
            Classify the intent and extract relevant information:
            
            INTENT TYPES:
            - goal_creation: User wants to create a new goal
            - daily_checkin: User wants to check in on progress
            - progress_review: User wants to see their progress/stats
            - motivation_request: User needs encouragement/motivation
            - goal_modification: User wants to change an existing goal
            - rating_response: User is giving a 1-10 rating
            - yes_no_response: User is answering yes/no
            - general_conversation: General chat/greeting
            
            For goal_creation, also extract:
            - goal_category: fitness, sobriety, meditation, therapy, habits, career, etc.
            - goal_title: Suggested title for the goal
            - goal_description: What the user wants to achieve
            
            For rating_response, extract:
            - rating: The numeric rating (1-10)
            
            For yes_no_response, extract:
            - answer: true for yes, false for no
            
            Return JSON format:
            {{
                "intent": "intent_type",
                "confidence": 0.0-1.0,
                "extracted_data": {{
                    // relevant extracted information
                }},
                "reasoning": "brief explanation"
            }}
            """
            
            response = self.model.generate_content(prompt)
            result = self._parse_json_response(response.text)
            
            if result:
                return result
            else:
                return self._fallback_intent_analysis(user_text)
                
        except Exception as e:
            logger.error(f"❌ Error in intent analysis: {e}")
            return self._fallback_intent_analysis(user_text)
    
    async def generate_goal_response(self, user_text: str, goal_created: bool, goal_data: Dict[str, Any] = None) -> str:
        """Generate response for goal creation"""
        try:
            if not self.initialized or not self.model:
                return self._fallback_goal_response(goal_created, goal_data)
            
            prompt = f"""
            Generate an encouraging response for a user who just created an accountability goal.
            
            User's original message: "{user_text}"
            Goal was created successfully: {goal_created}
            Goal details: {json.dumps(goal_data or {}, indent=2)}
            
            Create a response that:
            - Celebrates their commitment
            - Shows enthusiasm for their goal
            - Mentions specific details about their goal
            - Encourages them about the journey ahead
            - Offers to help with daily check-ins
            
            Keep it warm, encouraging, and personalized. Use emojis appropriately.
            Maximum 2-3 sentences.
            """
            
            response = self.model.generate_content(prompt)
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"❌ Error generating goal response: {e}")
            return self._fallback_goal_response(goal_created, goal_data)
    
    async def generate_checkin_response(self, checkin_data: Dict[str, Any], goal_data: Dict[str, Any] = None, streak_data: Dict[str, Any] = None) -> str:
        """Generate response for daily check-ins"""
        try:
            if not self.initialized or not self.model:
                return self._fallback_checkin_response(checkin_data)
            
            prompt = f"""
            Generate an encouraging response for a user's daily accountability check-in.
            
            Check-in data: {json.dumps(checkin_data, indent=2)}
            Goal data: {json.dumps(goal_data or {}, indent=2)}
            Streak data: {json.dumps(streak_data or {}, indent=2)}
            
            Create a response that:
            - Acknowledges their check-in
            - Celebrates their progress (if positive)
            - Offers encouragement (if struggling)
            - Mentions their streak if applicable
            - Motivates them for tomorrow
            
            Tone should be:
            - Supportive and understanding
            - Enthusiastic for successes
            - Compassionate for struggles
            - Forward-looking and hopeful
            
            Use emojis appropriately. Maximum 2-3 sentences.
            """
            
            response = self.model.generate_content(prompt)
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"❌ Error generating check-in response: {e}")
            return self._fallback_checkin_response(checkin_data)
    
    async def generate_motivation_message(self, user_context: Dict[str, Any] = None) -> str:
        """Generate motivational message"""
        try:
            if not self.initialized or not self.model:
                return self._fallback_motivation_message()
            
            prompt = f"""
            Generate a motivational message for someone working on accountability goals.
            
            User context: {json.dumps(user_context or {}, indent=2)}
            
            Create a message that:
            - Provides genuine encouragement
            - Acknowledges that growth is challenging
            - Emphasizes progress over perfection
            - Inspires them to keep going
            - Feels personal and authentic
            
            Keep it warm, uplifting, and empowering.
            Use emojis appropriately. 1-2 sentences.
            """
            
            response = self.model.generate_content(prompt)
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"❌ Error generating motivation message: {e}")
            return self._fallback_motivation_message()
    
    async def extract_goal_details(self, user_text: str) -> Dict[str, Any]:
        """Extract goal details from user text"""
        try:
            if not self.initialized or not self.model:
                return self._fallback_goal_extraction(user_text)
            
            prompt = f"""
            Extract goal details from this user message:
            
            "{user_text}"
            
            Extract and categorize:
            - goal_category: fitness, sobriety, meditation, therapy, habits, career, relationships, mental_health, other
            - goal_title: A clear, motivating title (max 50 chars)
            - goal_description: What they want to achieve
            - motivation: Why this matters to them (if mentioned)
            - frequency: How often they want to work on it (daily, weekly, etc.)
            - specific_actions: Concrete actions they mentioned
            
            Return JSON format:
            {{
                "goal_category": "category",
                "goal_title": "title",
                "goal_description": "description", 
                "motivation": "why this matters",
                "frequency": "how often",
                "specific_actions": ["action1", "action2"],
                "confidence": 0.0-1.0
            }}
            """
            
            response = self.model.generate_content(prompt)
            result = self._parse_json_response(response.text)
            
            if result:
                return result
            else:
                return self._fallback_goal_extraction(user_text)
                
        except Exception as e:
            logger.error(f"❌ Error extracting goal details: {e}")
            return self._fallback_goal_extraction(user_text)
    
    def _parse_json_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response"""
        try:
            # Try to find JSON in the response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
        except Exception as e:
            logger.error(f"❌ Error parsing JSON response: {e}")
        return None
    
    # === FALLBACK METHODS ===
    
    def _fallback_intent_analysis(self, user_text: str) -> Dict[str, Any]:
        """Fallback intent analysis without LLM"""
        user_text_lower = user_text.lower().strip()
        
        # Goal creation patterns
        if any(word in user_text_lower for word in ["goal", "want to", "help me", "start", "quit", "stop", "sober", "meditation", "exercise"]):
            return {
                "intent": "goal_creation",
                "confidence": 0.7,
                "extracted_data": {},
                "reasoning": "Detected goal creation keywords"
            }
        
        # Check-in patterns
        elif any(word in user_text_lower for word in ["check in", "progress", "how am i", "doing", "today"]):
            return {
                "intent": "daily_checkin", 
                "confidence": 0.7,
                "extracted_data": {},
                "reasoning": "Detected check-in keywords"
            }
        
        # Rating patterns
        elif re.search(r'\b([1-9]|10)\b', user_text_lower):
            numbers = re.findall(r'\b([1-9]|10)\b', user_text_lower)
            if numbers:
                return {
                    "intent": "rating_response",
                    "confidence": 0.8,
                    "extracted_data": {"rating": int(numbers[0])},
                    "reasoning": "Found numeric rating"
                }
        
        # Yes/No patterns
        elif re.search(r'\b(yes|yeah|yep|sure|no|nope|not really)\b', user_text_lower):
            is_yes = any(word in user_text_lower for word in ["yes", "yeah", "yep", "sure"])
            return {
                "intent": "yes_no_response",
                "confidence": 0.8,
                "extracted_data": {"answer": is_yes},
                "reasoning": "Found yes/no response"
            }
        
        # Motivation request
        elif any(word in user_text_lower for word in ["struggling", "hard", "difficult", "motivation", "encourage"]):
            return {
                "intent": "motivation_request",
                "confidence": 0.7,
                "extracted_data": {},
                "reasoning": "Detected need for motivation"
            }
        
        # Default to general conversation
        else:
            return {
                "intent": "general_conversation",
                "confidence": 0.5,
                "extracted_data": {},
                "reasoning": "No specific intent detected"
            }
    
    def _fallback_goal_response(self, goal_created: bool, goal_data: Dict[str, Any] = None) -> str:
        """Fallback goal creation response"""
        if goal_created and goal_data:
            title = goal_data.get("title", "your goal")
            return f"🎯 Awesome! I've set up your '{title}' goal! I'm here to support you every step of the way. Ready for your first check-in?"
        elif goal_created:
            return "🎯 Great! Your goal has been created! I'm excited to help you track your progress and celebrate your wins!"
        else:
            return "I had trouble creating your goal, but your commitment is what matters most! Let's try again."
    
    def _fallback_checkin_response(self, checkin_data: Dict[str, Any]) -> str:
        """Fallback check-in response"""
        score = checkin_data.get("overall_score", 0)
        if score >= 8:
            return f"🌟 Amazing! You're crushing it with that {score}/10! Keep up the incredible work!"
        elif score >= 6:
            return f"👏 Great job with that {score}/10! You're building strong habits!"
        elif score >= 4:
            return f"💪 Thanks for being honest with that {score}/10. Every step forward counts!"
        else:
            return f"🌅 I appreciate your honesty with that {score}/10. Tomorrow is a fresh start!"
    
    def _fallback_motivation_message(self) -> str:
        """Fallback motivation message"""
        messages = [
            "💪 You're stronger than you know! Every day you show up is a victory!",
            "🌟 Progress isn't always linear, but you're moving forward! Keep going!",
            "🌱 Every small step is still a step forward. You're building something amazing!",
            "💚 Your commitment to growth is inspiring! You've got this!",
            "✨ Remember: you're not just changing habits, you're becoming who you want to be!"
        ]
        import random
        return random.choice(messages)
    
    def _fallback_goal_extraction(self, user_text: str) -> Dict[str, Any]:
        """Fallback goal extraction"""
        user_text_lower = user_text.lower()
        
        # Simple category detection
        if "sober" in user_text_lower or "alcohol" in user_text_lower:
            category = "sobriety"
            title = "Stay Sober"
        elif "meditat" in user_text_lower or "mindful" in user_text_lower:
            category = "meditation"
            title = "Daily Meditation"
        elif any(word in user_text_lower for word in ["exercise", "fitness", "workout", "gym"]):
            category = "fitness"
            title = "Daily Exercise"
        elif "therapy" in user_text_lower or "counseling" in user_text_lower:
            category = "therapy"
            title = "Therapy Sessions"
        else:
            category = "habits"
            title = "Personal Goal"
        
        return {
            "goal_category": category,
            "goal_title": title,
            "goal_description": user_text[:100],
            "motivation": "",
            "frequency": "daily",
            "specific_actions": [],
            "confidence": 0.6
        }
