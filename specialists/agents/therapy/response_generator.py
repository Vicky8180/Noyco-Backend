"""
Response Generator for Therapy Check-In Agent
Generates empathetic, supportive responses for different scenarios
"""

import logging
import random
from typing import Dict, List, Optional, Any
from datetime import datetime

from .schema import RiskLevel, CheckpointState

logger = logging.getLogger(__name__)

class TherapyResponseGenerator:
    """Generates contextual, empathetic responses for therapy interactions"""
    
    def __init__(self):
        self.greetings = [
            "Hi, just checking in — how are you feeling today?",
            "Hello there. I'm here to check in with you today. How are you feeling?",
            "Good to see you. How are you feeling right now?",
            "I'm here for our check-in. How are you feeling today?"
        ]
        
        self.mood_rating_prompts = [
            "On a scale of 1-10, how would you rate your mood right now?",
            "Could you rate your current mood from 1-10? (1 being lowest, 10 being highest)",
            "How would you rate your mood today on a scale from 1-10?",
            "From 1-10, where would you place your mood right now?"
        ]
        
        self.feeling_prompts = [
            "Could you share 1-3 words that describe your feelings right now?",
            "What words would best describe how you're feeling today?",
            "Can you describe your current feelings in a few words?",
            "What emotions are you experiencing right now?"
        ]
        
        self.breathing_offers = [
            "Would you like to try a quick breathing exercise? I can guide you through a 2 or 5 minute session.",
            "Taking a moment to breathe can help. Would you like to try a short 2 or 5 minute breathing exercise?",
            "I can guide you through a brief breathing exercise if you'd like. Would a 2 or 5 minute session help?",
            "Sometimes a breathing exercise can help center us. Would you like to try one for 2 or 5 minutes?"
        ]
        
        self.breathing_instructions = {
            "start": [
                "Let's begin. Find a comfortable position and gently close your eyes if you'd like.",
                "Find a comfortable position. You can close your eyes if that feels right for you.",
                "Let's start. Sit comfortably and close your eyes if you wish."
            ],
            "inhale": [
                "Breathe in slowly through your nose for 4 counts...",
                "Take a slow, deep breath in through your nose...",
                "Inhale deeply and slowly..."
            ],
            "hold": [
                "Hold your breath gently for 2 counts...",
                "Hold this breath briefly...",
                "Pause for a moment..."
            ],
            "exhale": [
                "Now exhale slowly through your mouth for 6 counts...",
                "Release your breath slowly through your mouth...",
                "Exhale completely and slowly..."
            ],
            "continue": [
                "Continue this rhythm. Breathe in... hold... and breathe out...",
                "Keep breathing. In... hold... and out...",
                "Maintain this gentle rhythm of breathing..."
            ],
            "complete": [
                "Take one more deep breath in... and out. When you're ready, gently open your eyes.",
                "Last breath in... and out. Slowly return your awareness to the room.",
                "Final breath. In... and out. Gently open your eyes when you're ready."
            ]
        }
        
        self.closing_messages = [
            "Thanks for checking in today. Remember, small steps matter.",
            "Thank you for sharing with me today. Remember that each check-in is a positive step.",
            "I appreciate you taking time for this check-in. Every moment of self-care counts.",
            "Thank you for checking in. Remember to be gentle with yourself."
        ]
        
        self.crisis_messages = {
            "us": "I'm concerned about what you've shared. If you're in immediate danger, please call the National Suicide Prevention Lifeline at 988 or text HOME to 741741 to reach the Crisis Text Line. Would you like me to provide more resources?",
            "uk": "I'm concerned about what you've shared. If you're in immediate danger, please call the Samaritans at 116 123 or text SHOUT to 85258. Would you like me to provide more resources?",
            "au": "I'm concerned about what you've shared. If you're in immediate danger, please call Lifeline at 13 11 14 or text 0477 13 11 14. Would you like me to provide more resources?",
            "default": "I'm concerned about what you've shared. If you're in immediate danger, please contact your local emergency services or crisis helpline immediately. Would you like me to provide more resources?"
        }
        
        self.mood_responses = {
            "low": [
                "I'm sorry to hear you're feeling this way. That sounds really difficult.",
                "Thank you for sharing that with me. It takes courage to acknowledge these feelings.",
                "I hear that you're going through a tough time right now.",
                "It sounds like things are quite challenging for you at the moment."
            ],
            "medium": [
                "Thank you for sharing how you're feeling. It sounds like you're managing.",
                "I appreciate your honesty about where you're at today.",
                "It seems like you're having an okay day, with some ups and downs.",
                "Thanks for sharing. It sounds like you're hanging in there."
            ],
            "high": [
                "It's great to hear you're feeling positive today.",
                "I'm glad to hear you're doing well today.",
                "That's wonderful to hear. I'm happy that you're feeling good.",
                "It's really nice to hear that you're in a good place today."
            ]
        }
        
        self.weekly_summary_intros = [
            "Here's a quick summary of your past week:",
            "Looking at your check-ins from the past week:",
            "Here's what I've noticed from your recent check-ins:",
            "Based on your mood entries from the past week:"
        ]
        
        self.disclaimer = "I'm not a licensed professional, but I'm here to support and help you find resources."
        
    def generate_greeting(self) -> str:
        """Generate a warm greeting to start the conversation"""
        return random.choice(self.greetings)
        
    def generate_mood_rating_prompt(self) -> str:
        """Generate a prompt asking for mood rating"""
        return random.choice(self.mood_rating_prompts)
        
    def generate_feeling_prompt(self) -> str:
        """Generate a prompt asking for feeling words"""
        return random.choice(self.feeling_prompts)
        
    def generate_breathing_offer(self) -> str:
        """Generate an offer for breathing exercises"""
        return random.choice(self.breathing_offers)
        
    def generate_breathing_instruction(self, stage: str) -> str:
        """Generate breathing exercise instruction based on stage"""
        if stage in self.breathing_instructions:
            return random.choice(self.breathing_instructions[stage])
        return "Continue breathing slowly and mindfully."
        
    def generate_closing_message(self) -> str:
        """Generate a closing message for the conversation"""
        return random.choice(self.closing_messages)
        
    def generate_crisis_message(self, locale: str = "us") -> str:
        """Generate a crisis response message based on locale"""
        if locale.lower() in self.crisis_messages:
            return self.crisis_messages[locale.lower()]
        return self.crisis_messages["default"]
        
    def generate_mood_response(self, mood_score: int, feelings: List[str] = None) -> str:
        """Generate a response to the user's mood rating"""
        category = "medium"
        if mood_score <= 3:
            category = "low"
        elif mood_score >= 8:
            category = "high"
            
        response = random.choice(self.mood_responses[category])
        
        # Add reference to feelings if provided
        if feelings and len(feelings) > 0:
            feelings_str = ", ".join(feelings)
            feeling_references = [
                f" I understand you're feeling {feelings_str}.",
                f" Those feelings of {feelings_str} are valid.",
                f" It makes sense that you'd feel {feelings_str}."
            ]
            response += random.choice(feeling_references)
            
        return response
        
    def generate_weekly_summary_response(self, summary: Dict[str, Any]) -> str:
        """Generate a response for the weekly mood summary"""
        intro = random.choice(self.weekly_summary_intros)
        
        avg_mood = summary.get("avgMood", 5)
        trend = summary.get("trend", "flat")
        streak_days = summary.get("streakDays", 0)
        
        # Build the summary message
        message = f"{intro}\n\n"
        
        # Add mood average
        if avg_mood <= 3:
            message += f"Your average mood was {avg_mood:.1f}/10. It looks like it's been a challenging week. "
        elif avg_mood <= 6:
            message += f"Your average mood was {avg_mood:.1f}/10. You've had some ups and downs this week. "
        else:
            message += f"Your average mood was {avg_mood:.1f}/10. Overall, you've been feeling relatively positive. "
        
        # Add trend information
        if trend == "up":
            message += "Your mood has been improving over the week, which is great to see. "
        elif trend == "down":
            message += "Your mood has been declining somewhat over the week. "
        else:
            message += "Your mood has been relatively stable throughout the week. "
        
        # Add streak information
        if streak_days > 0:
            message += f"You've checked in for {streak_days} consecutive days - that's a great commitment to your wellbeing! "
        
        # Add encouragement
        encouragements = [
            "Remember that tracking your mood is an important step in managing your mental health.",
            "Each check-in helps you become more aware of your emotional patterns.",
            "Noticing these patterns can help you identify what affects your mood.",
            "Consistent check-ins like yours help build self-awareness."
        ]
        message += random.choice(encouragements)
        
        return message
        
    def detect_risk_level(self, text: str) -> int:
        """Detect risk level from user text (simplified version)"""
        # This is a simplified version - in production, this would use more sophisticated NLP
        high_risk_terms = [
            "kill myself", "suicide", "end my life", "don't want to live",
            "better off dead", "want to die", "harm myself"
        ]
        
        moderate_risk_terms = [
            "hopeless", "can't go on", "what's the point", "no reason to live",
            "no future", "giving up", "too much pain"
        ]
        
        low_risk_terms = [
            "depressed", "anxious", "struggling", "overwhelmed",
            "exhausted", "can't cope", "lonely"
        ]
        
        text_lower = text.lower()
        
        # Check for high risk terms
        for term in high_risk_terms:
            if term in text_lower:
                return RiskLevel.HIGH
                
        # Check for moderate risk terms
        for term in moderate_risk_terms:
            if term in text_lower:
                return RiskLevel.MODERATE
                
        # Check for low risk terms
        for term in low_risk_terms:
            if term in text_lower:
                return RiskLevel.LOW
                
        return RiskLevel.NONE
