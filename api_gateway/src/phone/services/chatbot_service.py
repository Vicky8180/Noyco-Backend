
# import asyncio
# import json
# import logging
# from typing import Optional, Dict, Any, AsyncGenerator, List
# from functools import lru_cache
# import google.generativeai as genai
# from google.generativeai.types import HarmCategory, HarmBlockThreshold
# from fastapi import HTTPException
# from fastapi.responses import StreamingResponse
# import time

# from ..config import settings
# from ..schema import ChatbotRequest, ChatbotResponse

# logger = logging.getLogger(__name__)

# # Concurrency control
# MAX_CONCURRENT_REQUESTS = 15
# request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

# class ChatbotService:
#     """Chatbot service using Google Gemini with ultra-low latency streaming"""

#     def __init__(self):
#         """Initialize Gemini client with optimized settings"""
#         genai.configure(api_key=settings.GEMINI_API_KEY)

#         # Configure safety settings for production
#         self.safety_settings = {
#             HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
#             HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
#             HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
#             HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
#         }

#         # Initialize model with optimized generation config
#         generation_config = genai.types.GenerationConfig(
#             temperature=0.7,
#             top_p=0.8,
#             top_k=40,
#             max_output_tokens=150,  # Shorter responses for voice
#             candidate_count=1
#         )

#         self.model = genai.GenerativeModel(
#             model_name=settings.GEMINI_MODEL,
#             safety_settings=self.safety_settings,
#             generation_config=generation_config
#         )

#         # System prompt optimized for voice conversations
#         self.system_prompt = """You are a helpful AI voice assistant in a phone conversation.

# IMPORTANT CONVERSATION RULES:
# - Keep responses SHORT and CONVERSATIONAL (1-3 sentences max)
# - Speak naturally as if talking on the phone
# - Acknowledge what you heard before responding
# - Ask follow-up questions to keep conversation flowing
# - Use everyday language, avoid technical jargon
# - Respond immediately, don't wait for more information
# - Be helpful and engaging
# - If uncertain, ask for clarification rather than guessing

# Remember: This is a VOICE conversation - be concise and natural!"""

#         # Pre-built common responses for ultra-low latency
#         self.quick_responses = {
#             "hello": "Hello! How can I help you today?",
#             "hi": "Hi there! What can I do for you?",
#             "thanks": "You're welcome! Is there anything else I can help you with?",
#             "thank you": "My pleasure! Let me know if you need anything else.",
#             "yes": "Great! How would you like me to help?",
#             "no": "No problem. What else can I assist you with?",
#             "bye": "Goodbye! Have a great day!",
#             "goodbye": "Take care! Feel free to call anytime."
#         }

#     async def handle_streaming_chatbot_request(self, request: ChatbotRequest):
#         """Handle streaming chatbot request from route"""
#         try:
#             async def generate_response() -> AsyncGenerator[str, None]:
#                 try:
#                     async with request_semaphore:
#                         async for chunk in self.get_streaming_response(request.userText, request.context):
#                             if chunk:
#                                 yield f"data: {json.dumps({'response': chunk})}\n\n"
#                         yield f"data: {json.dumps({'response': '[DONE]'})}\n\n"
#                 except Exception as e:
#                     logger.error(f"Error in streaming response: {str(e)}")
#                     yield f"data: {json.dumps({'response': f'Error: {str(e)}'})}\n\n"

#             return StreamingResponse(
#                 generate_response(),
#                 media_type="text/plain",
#                 headers={
#                     "Cache-Control": "no-cache",
#                     "Connection": "keep-alive",
#                     "Access-Control-Allow-Origin": "*",
#                     "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
#                     "Access-Control-Allow-Headers": "Content-Type, Authorization",
#                 }
#             )

#         except Exception as e:
#             logger.error(f"Error in chatbot endpoint: {str(e)}")
#             raise HTTPException(status_code=500, detail=str(e))

#     async def get_streaming_response(self, user_text: str, context: Optional[List[Dict]] = None) -> AsyncGenerator[str, None]:
#         """
#         Get ultra-low latency streaming response from the chatbot
#         """
#         try:
#             # Clean and normalize input
#             user_text = user_text.strip().lower()

#             # Check for quick responses first (ultra-low latency)
#             quick_response = self._get_quick_response(user_text)
#             if quick_response:
#                 logger.info(f"Quick response for '{user_text}': {quick_response}")
#                 yield quick_response
#                 return

#             # Build context-aware prompt
#             prompt = self._build_context_prompt(user_text, context)

#             # Generate streaming response with timeout
#             try:
#                 response = await asyncio.wait_for(
#                     asyncio.get_event_loop().run_in_executor(
#                         None,
#                         lambda: self.model.generate_content(prompt, stream=True)
#                     ),
#                     timeout=5.0  # 5 second timeout
#                 )

#                 if response:
#                     accumulated_text = ""
#                     sentence_buffer = ""
#                     word_count = 0

#                     for chunk in response:
#                         if chunk.text:
#                             chunk_text = chunk.text
#                             accumulated_text += chunk_text
#                             sentence_buffer += chunk_text

#                             # Count words for chunking
#                             words = sentence_buffer.split()
#                             word_count = len(words)

#                             # Yield complete thoughts more aggressively for voice
#                             should_yield = any([
#                                 sentence_buffer.endswith(('.', '!', '?')),  # Complete sentences
#                                 sentence_buffer.endswith((',', ';', ':')),  # Natural pauses
#                                 word_count >= 5,  # Every 5 words
#                                 len(sentence_buffer) >= 30  # Every 30 characters
#                             ])

#                             if should_yield and sentence_buffer.strip():
#                                 clean_text = sentence_buffer.strip()
#                                 if clean_text:
#                                     yield clean_text
#                                     sentence_buffer = ""
#                                     word_count = 0

#                     # Yield any remaining text
#                     if sentence_buffer.strip():
#                         yield sentence_buffer.strip()

#                 else:
#                     yield "I'm not sure I understood that. Could you please rephrase?"

#             except asyncio.TimeoutError:
#                 logger.warning(f"Response generation timeout for: {user_text}")
#                 yield "I'm thinking about that. Could you give me a moment?"

#         except Exception as e:
#             logger.error(f"Error getting streaming response: {str(e)}")
#             yield "I'm having trouble processing that. Could you try again?"

#     def _get_quick_response(self, user_text: str) -> Optional[str]:
#         """Get quick response for common phrases"""
#         # Normalize text
#         text = user_text.lower().strip()

#         # Check exact matches first
#         if text in self.quick_responses:
#             return self.quick_responses[text]

#         # Check partial matches for greetings
#         if any(greeting in text for greeting in ["hello", "hi", "hey"]):
#             return "Hello! How can I help you today?"

#         if any(thanks in text for thanks in ["thank", "thanks"]):
#             return "You're welcome! Anything else I can help with?"

#         if any(bye in text for bye in ["bye", "goodbye", "see you"]):
#             return "Goodbye! Have a great day!"

#         # Check for yes/no responses
#         if text in ["yes", "yeah", "yep", "sure", "okay", "ok"]:
#             return "Great! How can I help you?"

#         if text in ["no", "nope", "not really"]:
#             return "No problem. What else can I do for you?"

#         return None

#     def _build_context_prompt(self, user_text: str, context: Optional[List[Dict]] = None) -> str:
#         """Build context-aware prompt for better conversation flow"""
#         prompt_parts = [self.system_prompt]

#         # Add recent conversation context
#         if context and len(context) > 0:
#             prompt_parts.append("\nRecent conversation:")

#             # Include last 3 exchanges for context
#             recent_context = context[-3:]
#             for exchange in recent_context:
#                 if "user" in exchange:
#                     prompt_parts.append(f"User: {exchange['user']}")
#                 if "assistant" in exchange:
#                     prompt_parts.append(f"Assistant: {exchange['assistant']}")

#         prompt_parts.append(f"\nUser: {user_text}")
#         prompt_parts.append("Assistant:")

#         return "\n".join(prompt_parts)

#     @lru_cache(maxsize=100)
#     def _cache_response(self, text_hash: str) -> Optional[str]:
#         """Cache responses for repeated queries"""
#         # This would integrate with a proper cache in production
#         return None
