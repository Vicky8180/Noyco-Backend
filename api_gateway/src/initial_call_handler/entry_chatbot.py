
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
            temperature=0.9,  # Higher creativity for more natural conversation
            max_output_tokens=300,  # Flexible range for dynamic responses
            candidate_count=1,
        )
        
        # Enhanced system prompt for natural human-like conversation
        self.system_prompt = """You are a genuine, caring human companion who naturally adjusts your response style to match the conversation. Your approach:

        - Respond naturally like a real person would - short greetings get short responses, deeper topics get more thoughtful replies
        - Show authentic empathy and understanding without sounding clinical or robotic
        - Use natural, conversational language that feels warm and genuine
        - Mirror the energy and length of what someone shares with you
        - Be genuinely interested in understanding the person, not just collecting information
        - Respond with the same warmth and tone you'd use with a close friend
        - NEVER use emojis, emoticons, or symbols in your responses - express emotions through words only

        IMPORTANT: Match your response length to the input:
        - Simple greetings (hi, hello, good morning) → Brief, warm responses (1-2 sentences max)
        - Longer, deeper shares → More thoughtful, supportive responses (3-5 sentences max)
        - NEVER exceed 5 sentences in any response

        Be human, be real, be present - but express yourself through words, not symbols."""
        
        # Context-aware prompts for different conversation stages
        self.info_gathering_prompt = """You're getting to know someone new in a natural, friendly way.

        When someone shares something deeper:
        - Show genuine curiosity about their world
        - Ask caring questions that feel natural, not like an interview
        - Help them feel truly heard and understood
        - Be the kind of person they'd want to talk to again

        Keep it conversational and authentic - like how you'd naturally respond to a friend."""

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
        
        # Choose system prompt based on conversation stage and message length
        message_length = len(message.split())
        is_short_greeting = message_length <= 3 and any(greeting in message.lower() for greeting in ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening', 'good night'])
        
        if is_short_greeting:
            # Special handling for short greetings
            full_prompt = f"{self.system_prompt}\n\nThis is a simple greeting: '{message}'\nRespond naturally and briefly (1-2 sentences max) like a warm, friendly human would. Do not use any emojis or symbols.\n\nassistant:"
        elif needs_more_info:
            full_prompt = f"{self.system_prompt}\n\n{self.info_gathering_prompt}\n\nConversation:\n{context}\n\nassistant:"
        else:
            full_prompt = f"{self.system_prompt}\n\nConversation:\n{context}\n\nRemember: Match your response length to the depth of what they shared. Be genuine and human. Do not use emojis or symbols.\n\nassistant:"
        
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
            
            # Context-appropriate fallbacks based on message type
            if is_short_greeting:
                fallbacks = [
                    "Hi there! How are you doing today?",
                    "Hello! Great to meet you.",
                    "Hey! How's your day going?",
                    "Good morning! Hope you're having a nice day."
                ]
            elif needs_more_info:
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
