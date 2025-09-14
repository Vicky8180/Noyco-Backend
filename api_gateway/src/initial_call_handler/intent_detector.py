

# =======================
# intent_detector.py (OPTIMIZED FOR BACKGROUND PROCESSING)
# =======================

import google.generativeai as genai
import json
import re
from typing import List, Dict, Optional
import asyncio
import time
from .schema import IntentResult, ConversationMessage

class IntentDetector:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        # Use faster model for better latency
        self.model = genai.GenerativeModel('models/gemini-2.5-flash-lite')
        
        # Configure generation for optimal speed/accuracy balance
        self.generation_config = genai.types.GenerationConfig(
            temperature=0.2,  # Low temperature for consistent, reliable results
            max_output_tokens=400,  # Reasonable limit for analysis
            candidate_count=1,
        )
        
        # Optimized prompt for high-accuracy LLM-only intent detection
        self.intent_prompt_template = """
        Analyze this conversation to determine the user's primary support need. Focus on the emotional context and underlying needs.

        CONVERSATION:
        {context}

        ANALYZE FOR THESE SPECIFIC INTENTS:

        1. **emotional**: User is dealing with grief, loss, terminal illness, death of loved ones, bereavement, or similar devastating life events. Look for words like: died, death, funeral, grief, terminal, cancer, hospice, devastated, mourning, widow, bereaved, loss.

        2. **accountability**: User needs help with habit changes, addiction recovery, quitting behaviors, therapy compliance, or maintaining commitments. Look for: quit, quitting, sober, sobriety, addiction, recovery, relapse, stop smoking, drinking, therapy compliance, accountability, habit.

        3. **loneliness**: User expresses loneliness, social isolation, lack of meaningful connections, or need for regular social interaction. Look for: alone, lonely, isolated, no friends, no one to talk to, isolation, companionship, social support.

        4. **mental_therapy**: User seeks support for anxiety, depression, panic, PTSD, therapy needs, or mental health crisis situations. Look for: therapy, therapist, anxiety, depression, panic attacks, ptsd, mental health, counseling, psychiatric, crisis.

        5. **social_anxiety**: User needs help preparing for specific social events, presentations, interviews, dates, or performance situations. Look for: interview, presentation, public speaking, date, meeting, performance, social event, nervous about, prepare for.

        IMPORTANT: Only assign high confidence (80%+) if there are clear, specific indicators. If the conversation is too general or ambiguous, assign lower confidence and "none" intent.

        Return ONLY this JSON format:
        {{
            "intent": "intent_name_or_none",
            "confidence": 0.0-1.0,
            "reasoning": "specific evidence from conversation",
            "keywords": ["key", "phrases", "that", "support", "this"]
        }}
        """

    def detect_intent_with_gemini(self, conversation_history: List[ConversationMessage]) -> IntentResult:
        """Enhanced LLM-based intent detection focused on accuracy"""
        
        user_messages = [msg.content for msg in conversation_history if msg.role == "user"]
        if not user_messages:
            return IntentResult(
                intent="none",
                confidence=0.0,
                reasoning="No user messages available for analysis",
                keywords=[]
            )
        
        # Build comprehensive context - use more context for better accuracy
        context = ""
        for msg in conversation_history[-8:]:  # Use more context for accurate detection
            role_prefix = "User" if msg.role == "user" else "Assistant"
            # Don't truncate messages too aggressively - accuracy is priority
            content = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
            context += f"{role_prefix}: {content}\n"
        
        prompt = self.intent_prompt_template.format(context=context)
        
        try:
            start_time = time.time()
            
            response = self.model.generate_content(
                prompt,
                generation_config=self.generation_config
            )
            
            generation_time = time.time() - start_time
            # Suppress timing logs during startup
            # print(f"LLM intent detection took {generation_time:.2f}s")
            
            response_text = response.text.strip()
            
            # Enhanced JSON extraction with better error handling
            return self._extract_intent_result(response_text)
                
        except Exception as e:
            print(f"Error in LLM intent detection: {e}")
            # Return low confidence result instead of failing
            return IntentResult(
                intent="none",
                confidence=0.0,
                reasoning=f"Error in intent detection: {str(e)}",
                keywords=[]
            )

    def _extract_intent_result(self, response_text: str) -> IntentResult:
        """Enhanced extraction of intent result from LLM response"""
        
        # Try JSON extraction first
        json_match = re.search(r'\{[^}]*\}', response_text, re.DOTALL)
        if json_match:
            try:
                result_dict = json.loads(json_match.group())
                
                intent = result_dict.get("intent", "none").lower().strip()
                confidence = float(result_dict.get("confidence", 0.0))
                reasoning = result_dict.get("reasoning", "LLM analysis completed")
                keywords = result_dict.get("keywords", [])
                
                # Validate intent is one of our expected values
                valid_intents = ["emotional", "accountability", "loneliness", "mental_therapy", "social_anxiety", "none"]
                if intent not in valid_intents:
                    intent = "none"
                    confidence = 0.0
                    reasoning = f"Invalid intent detected: {intent}. " + reasoning
                
                # Ensure confidence is within bounds
                confidence = max(0.0, min(1.0, confidence))
                
                # Limit keywords
                keywords = keywords[:6] if isinstance(keywords, list) else []
                
                return IntentResult(
                    intent=intent,
                    confidence=confidence,
                    reasoning=reasoning,
                    keywords=keywords
                )
                
            except json.JSONDecodeError as e:
                print(f"JSON parsing failed: {e}")
                # Fall through to regex extraction
        
        # Fallback: regex-based extraction
        return self._parse_llm_response_fallback(response_text)

    def _parse_llm_response_fallback(self, response_text: str) -> IntentResult:
        """Robust regex-based parsing when JSON extraction fails"""
        
        # Extract intent
        intent_patterns = [
            r'(?:intent["\']?\s*:\s*["\']?)([^"\']*)',
            r'Intent:\s*([^\n,]*)',
            r'intent.*?([a-z_]+)',
        ]
        
        intent = "none"
        for pattern in intent_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                potential_intent = match.group(1).lower().strip()
                valid_intents =  ["emotional", "accountability", "loneliness", "mental_therapy", "social_anxiety", "none"]
                if potential_intent in valid_intents:
                    intent = potential_intent
                    break
        
        # Extract confidence
        confidence_patterns = [
            r'(?:confidence["\']?\s*:\s*)([0-9]*\.?[0-9]+)',
            r'Confidence:\s*([0-9]*\.?[0-9]+)',
            r'([0-9]+(?:\.[0-9]+)?)\s*%',
        ]
        
        confidence = 0.0
        for pattern in confidence_patterns:
            match = re.search(pattern, response_text)
            if match:
                try:
                    conf_value = float(match.group(1))
                    # Handle percentage format
                    if conf_value > 1.0:
                        conf_value = conf_value / 100.0
                    confidence = max(0.0, min(1.0, conf_value))
                    break
                except ValueError:
                    continue
        
        # Extract reasoning (first sentence or two)
        reasoning_match = re.search(r'(?:reasoning["\']?\s*:\s*["\']?)([^"\']*)', response_text, re.IGNORECASE)
        if reasoning_match:
            reasoning = reasoning_match.group(1).strip()[:200]  # Limit length
        else:
            reasoning = "Regex parsing of LLM response"
        
        return IntentResult(
            intent=intent,
            confidence=confidence,
            reasoning=reasoning,
            keywords=[]  # Keywords are harder to extract via regex
        )

    def create_timeout_fallback(self) -> IntentResult:
        """Create a fallback result when intent detection times out"""
        return IntentResult(
            intent="none",
            confidence=0.0,
            reasoning="Intent detection timeout - insufficient time for analysis",
            keywords=[]
        )
