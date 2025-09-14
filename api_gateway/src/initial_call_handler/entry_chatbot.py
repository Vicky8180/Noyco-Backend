
# =======================
# entry_chatbot.py (OPTIMIZED FOR FAST RESPONSE)
# =======================

import google.generativeai as genai
from typing import List
import time
from .schema import ConversationMessage

class EntryChatbot:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        # Use faster model for immediate responses
        self.model = genai.GenerativeModel('models/gemini-2.5-flash-lite')
        
        # Optimized for speed while maintaining quality
        self.generation_config = genai.types.GenerationConfig(
            temperature=0.8,  # Balanced creativity for natural conversation
            max_output_tokens=250,  # Concise but complete responses
            candidate_count=1,
        )
        
        # Streamlined system prompt for fast generation
        self.system_prompt = """You are a warm, empathetic AI companion. Your role:

        - Listen with genuine care and understanding
        - Ask thoughtful questions to learn about their situation
        - Be conversational, supportive, and human-like
        - Help them feel heard and understood

        Keep responses natural and engaging. Focus on understanding their needs and emotional state."""
        
        # Context-aware prompts for different conversation stages
        self.info_gathering_prompt = """You're in an initial conversation to understand what support this person needs.

        Be naturally curious about:
        - What's on their mind today
        - Their current situation or challenges  
        - What brings them here
        - How they're feeling

        Ask 1-2 thoughtful questions. Keep it conversational, not clinical."""

    def generate_response(self, message: str, conversation_history: List[ConversationMessage], needs_more_info: bool = False) -> str:
        """Generate fast, empathetic responses optimized for immediate delivery"""
        
        start_time = time.time()
        
        # Use minimal context for speed - only last 3 exchanges
        context = ""
        recent_messages = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
        
        for msg in recent_messages:
            # Truncate long messages for faster processing
            content = msg.content[:120] + "..." if len(msg.content) > 120 else msg.content
            context += f"{msg.role}: {content}\n"
        
        context += f"user: {message}\n"
        
        # Choose system prompt based on conversation stage
        if needs_more_info:
            full_prompt = f"{self.system_prompt}\n\n{self.info_gathering_prompt}\n\nConversation:\n{context}\n\nassistant:"
        else:
            full_prompt = f"{self.system_prompt}\n\nConversation:\n{context}\n\nassistant:"
        
        try:
            response = self.model.generate_content(
                full_prompt,
                generation_config=self.generation_config
            )
            
            generation_time = time.time() - start_time
            # Suppress timing logs during startup
            # print(f"Chatbot response generated in {generation_time:.2f}s")
            
            return response.text.strip()
            
        except Exception as e:
            print(f"Error generating response: {e}")
            
            # Fast, contextually appropriate fallbacks
            if needs_more_info:
                fallbacks = [
                    "I'd love to understand how I can best help you. What's been on your mind lately?",
                    "Tell me more about what's going on. I'm here to listen and support you.",
                    "I want to make sure I understand your situation. What would be most helpful to talk about?",
                    "What brings you here today? I'm here to help however I can."
                ]
            else:
                fallbacks = [
                    "I'm here to listen and support you. How are you feeling about everything?",
                    "Thank you for sharing that with me. I want to understand how I can help.",
                    "I hear you. What's the most important thing on your mind right now?",
                    "That sounds like a lot to handle. I'm here for you."
                ]
            
            # Consistent fallback selection based on message content
            fallback_index = abs(hash(message)) % len(fallbacks)
            return fallbacks[fallback_index]
