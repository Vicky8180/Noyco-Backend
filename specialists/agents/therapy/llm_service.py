"""
LLM Service for Therapy Check-In Agent
Handles advanced natural language processing using Gemini API
"""

import logging
import re
import json
from typing import Dict, List, Optional, Any, Tuple
import google.generativeai as genai
import asyncio
from concurrent.futures import ThreadPoolExecutor
from ..config import get_settings

logger = logging.getLogger(__name__)

# Thread pool to off-load blocking Gemini calls
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="therapy-llm")

class TherapyLLMService:
    """Service for LLM-powered features in the therapy agent"""
    
    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = settings.LLM_ENGINE
        self.initialized = False
        
    async def initialize(self):
        """Initialize the LLM service"""
        try:
            if not self.api_key:
                logger.error("❌ Missing API key for Therapy LLM Service")
                return False
                
            genai.configure(api_key=self.api_key)
            self.initialized = True
            logger.info("✅ Therapy LLM Service initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Therapy LLM Service: {e}")
            return False
            
    async def extract_feelings(self, text: str) -> List[str]:
        """Extract feeling words from user text"""
        # Define common feelings for fallback and pattern matching
        common_feelings = [
            "happy", "sad", "anxious", "calm", "stressed", "overwhelmed", "tired", 
            "energetic", "hopeful", "hopeless", "angry", "frustrated", "excited", 
            "nervous", "worried", "content", "peaceful", "irritated", "depressed", 
            "cheerful", "joyful", "gloomy", "scared", "afraid", "confident", 
            "insecure", "proud", "ashamed", "grateful", "resentful", "lonely"
        ]
        
        # First try direct word matching
        text_lower = text.lower()
        direct_matches = [word for word in common_feelings if word in text_lower]
        
        # If we found at least 2 feelings through direct matching, return those
        if len(direct_matches) >= 2:
            logger.info(f"✅ Extracted feelings through direct matching: {direct_matches[:3]}")
            return direct_matches[:3]
            
        # Try pattern matching for "feeling X" or "I feel X"
        feeling_patterns = [
            r'(?:feel|feeling|felt)\s+(\w+)',  # "feeling happy", "I feel sad"
            r'(?:am|\'m)\s+(\w+)',  # "I'm anxious"
        ]
        
        pattern_matches = []
        for pattern in feeling_patterns:
            matches = re.findall(pattern, text_lower)
            pattern_matches.extend(matches)
        
        # Filter pattern matches to only include actual feelings
        valid_pattern_matches = [word for word in pattern_matches if word in common_feelings]
        if valid_pattern_matches:
            logger.info(f"✅ Extracted feelings through pattern matching: {valid_pattern_matches[:3]}")
            return valid_pattern_matches[:3]
            
        # If we have any direct matches, return those
        if direct_matches:
            logger.info(f"✅ Extracted feelings (limited direct matches): {direct_matches}")
            return direct_matches
        
        # If LLM service is not initialized, use fallback extraction
        if not self.initialized:
            # Fallback - extract any feeling-adjacent words
            fallback_feelings = []
            for sentence in text.split('.'):
                for feeling in common_feelings:
                    if feeling in sentence.lower():
                        fallback_feelings.append(feeling)
            
            if fallback_feelings:
                logger.info(f"✅ Extracted feelings (fallback): {fallback_feelings[:3]}")
                return fallback_feelings[:3]
            
            # Ultimate fallback - return some generic feelings based on text sentiment
            if any(word in text_lower for word in ["good", "great", "nice", "happy", "well"]):
                logger.info("✅ Using positive sentiment fallback feelings")
                return ["happy", "content"]
            elif any(word in text_lower for word in ["bad", "sad", "upset", "worried", "stress"]):
                logger.info("✅ Using negative sentiment fallback feelings")
                return ["worried", "stressed"]
            else:
                logger.info("✅ Using neutral fallback feelings")
                return ["neutral", "contemplative"]
        
        # Use LLM for more sophisticated extraction
        try:
            prompt = f"""
            Extract exactly 2-3 feeling words from the text below. Return ONLY a JSON array of strings with no explanation.
            Example: ["happy", "excited"]
            
            Common feeling words include: happy, sad, anxious, calm, stressed, overwhelmed, tired, 
            energetic, hopeful, hopeless, angry, frustrated, excited, nervous, worried, content, 
            peaceful, irritated, depressed, cheerful, joyful, gloomy, scared, afraid, confident.
            
            Text: "{text}"
            
            Feeling words (JSON array only):
            """
            
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                _EXECUTOR,
                self._generate_content_sync,
                prompt,
                0.1,  # Low temperature for consistent results
                300   # Short response
            )
            
            # Extract JSON array
            match = re.search(r'\[.*\]', response)
            if match:
                try:
                    feelings = json.loads(match.group(0))
                    logger.info(f"✅ Extracted feelings with LLM: {feelings[:3]}")
                    return feelings[:3]  # Limit to 3 feelings
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Failed to parse LLM response as JSON: {response}")
                    
            # Fallback to simple extraction from LLM response
            words = re.findall(r'"([^"]+)"', response)  # Extract quoted words
            if words:
                logger.info(f"✅ Extracted feelings from LLM quotes: {words[:3]}")
                return words[:3]
                
            # Last resort - extract words that might be feelings
            all_words = re.findall(r'\b\w+\b', response)
            feeling_words = [word for word in all_words if word.lower() in common_feelings]
            if feeling_words:
                logger.info(f"✅ Extracted common feelings from LLM response: {feeling_words[:3]}")
                return feeling_words[:3]
                
            # If all else fails, return generic feelings based on text sentiment
            if any(word in text_lower for word in ["good", "great", "nice", "happy"]):
                logger.info("✅ Using positive sentiment fallback feelings after LLM failure")
                return ["happy", "content"]
            else:
                logger.info("✅ Using neutral fallback feelings after LLM failure")
                return ["neutral", "contemplative"]
            
        except Exception as e:
            logger.error(f"❌ Error extracting feelings with LLM: {e}")
            # Return fallback feelings on LLM error
            logger.info("✅ Using fallback feelings after LLM error")
            return ["uncertain", "mixed"]
            
    async def analyze_risk_level(self, text: str) -> Tuple[int, str]:
        """Analyze risk level in user text"""
        # Comprehensive keyword lists for risk detection
        high_risk = [
            "suicide", "kill myself", "end my life", "want to die", "better off dead",
            "no reason to live", "can't take it anymore", "ending it all", 
            "take my own life", "don't want to be alive", "want to end it",
            "going to kill", "plan to end", "hurt myself", "self harm", "cut myself",
            "overdose", "jump off", "hang myself", "shoot myself"
        ]
        
        moderate_risk = [
            "hopeless", "can't go on", "no point", "giving up", "what's the point",
            "tired of living", "exhausted with life", "don't see a future",
            "everything is pointless", "no one would miss me", "everyone would be better off",
            "don't care anymore", "nothing matters", "no hope", "despair", "unbearable"
        ]
        
        low_risk = [
            "sad", "depressed", "anxious", "struggling", "difficult time",
            "feeling down", "overwhelmed", "stressed", "can't cope", "miserable"
        ]
        
        text_lower = text.lower()
        
        # First check for high risk keywords - immediate priority
        for term in high_risk:
            if term in text_lower:
                logger.warning(f"⚠️ HIGH RISK detected: '{term}' found in text")
                return 3, f"High risk language detected: '{term}'"
        
        # Then check for moderate risk phrases - need more context
        for term in moderate_risk:
            if term in text_lower:
                logger.warning(f"⚠️ MODERATE RISK detected: '{term}' found in text")
                return 2, f"Moderate risk language detected: '{term}'"
        
        # Check for low risk indicators
        for term in low_risk:
            if term in text_lower:
                logger.info(f"ℹ️ LOW RISK detected: '{term}' found in text")
                return 1, f"Low risk language detected: '{term}'"
        
        # If LLM is not initialized, return based on the keyword check results
        if not self.initialized:
            return 0, "No concerning language detected"
        
        # Use LLM for more sophisticated analysis if available
        try:
            prompt = f"""
            Analyze the following text for mental health risk level. Consider suicidal ideation, self-harm, severe depression, etc.
            Respond with ONLY a JSON object containing:
            1. "risk_level": integer from 0-3 (0=none, 1=low, 2=moderate, 3=high)
            2. "reason": brief explanation
            
            Guidelines:
            - Risk level 3 (HIGH): Clear suicidal ideation, specific plans, intent to harm self
            - Risk level 2 (MODERATE): Expressions of hopelessness, feeling trapped, no purpose
            - Risk level 1 (LOW): Expressions of sadness, depression without suicidal content
            - Risk level 0 (NONE): No concerning language
            
            Text: "{text}"
            
            JSON response:
            """
            
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                _EXECUTOR,
                self._generate_content_sync,
                prompt,
                0.0,  # Zero temperature for consistent results
                300   # Short response
            )
            
            # Extract JSON
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                try:
                    risk_data = json.loads(match.group(0))
                    risk_level = int(risk_data.get("risk_level", 0))
                    reason = risk_data.get("reason", "No specific reason provided")
                    
                    # Log the risk assessment
                    if risk_level >= 2:
                        logger.warning(f"⚠️ LLM detected RISK LEVEL {risk_level}: {reason}")
                    elif risk_level == 1:
                        logger.info(f"ℹ️ LLM detected LOW RISK: {reason}")
                    else:
                        logger.info(f"✅ LLM detected NO RISK: {reason}")
                        
                    return risk_level, reason
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"❌ Error parsing risk assessment JSON: {e}")
                    # Continue to fallback
            
            # If we reach here, LLM analysis failed, so use the keyword-based result
            # We already checked keywords, so we can return NONE if we got here
            return 0, "No concerning language detected after analysis"
                
        except Exception as e:
            logger.error(f"❌ Error analyzing risk level: {e}")
            # Return NONE since we already checked for keywords above
            return 0, "Error during risk analysis"
            
    async def generate_weekly_insights(self, mood_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate insights from weekly mood entries"""
        if not self.initialized or not mood_entries:
            # Simple fallback
            return {
                "avgMood": sum(entry.get("moodScore", 5) for entry in mood_entries) / len(mood_entries),
                "trend": "flat",
                "streakDays": len(mood_entries),
                "notes": ["Weekly summary generated with limited data"]
            }
        
        try:
            # Format entries for the prompt
            entries_text = "\n".join([
                f"Date: {entry.get('timestampISO', '')}, " +
                f"Mood: {entry.get('moodScore', 0)}/10, " +
                f"Feelings: {', '.join(entry.get('feelings', []))}"
                for entry in mood_entries
            ])
            
            prompt = f"""
            Analyze these mood entries and generate a weekly summary. Return ONLY a JSON object with:
            - "avgMood": float (average mood score)
            - "trend": string ("up", "down", or "flat")
            - "streakDays": integer (number of consecutive days)
            - "notes": array of strings (2-3 insights about patterns)
            
            Mood Entries:
            {entries_text}
            
            JSON summary:
            """
            
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                _EXECUTOR,
                self._generate_content_sync,
                prompt,
                0.2,  # Low temperature for consistent results
                500   # Moderate response length
            )
            
            # Extract JSON object
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group(0))
                    # Ensure all required fields are present
                    result["avgMood"] = float(result.get("avgMood", 5.0))
                    result["trend"] = result.get("trend", "flat")
                    result["streakDays"] = int(result.get("streakDays", len(mood_entries)))
                    result["notes"] = result.get("notes", ["Weekly summary generated"])
                    return result
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"❌ Error parsing weekly insights JSON: {e}")
                    
            # Calculate fallback values
            avg_mood = sum(entry.get("moodScore", 5) for entry in mood_entries) / len(mood_entries)
            
            # Simple trend calculation
            if len(mood_entries) >= 2:
                first_half = mood_entries[:len(mood_entries)//2]
                second_half = mood_entries[len(mood_entries)//2:]
                first_avg = sum(entry.get("moodScore", 5) for entry in first_half) / len(first_half)
                second_avg = sum(entry.get("moodScore", 5) for entry in second_half) / len(second_half)
                
                if second_avg - first_avg > 0.5:
                    trend = "up"
                elif first_avg - second_avg > 0.5:
                    trend = "down"
                else:
                    trend = "flat"
            else:
                trend = "flat"
                
            return {
                "avgMood": avg_mood,
                "trend": trend,
                "streakDays": len(mood_entries),
                "notes": ["Weekly summary generated with limited analysis"]
            }
            
        except Exception as e:
            logger.error(f"❌ Error generating weekly insights: {e}")
            return {
                "avgMood": 5.0,
                "trend": "flat",
                "streakDays": 0,
                "notes": [f"Error generating insights: {str(e)}"]
            }
            
    def _generate_content_sync(self, prompt: str, temperature: float = 0.2, max_output_tokens: int = 800) -> str:
        """Synchronous wrapper for Gemini content generation"""
        try:
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                top_p=0.8,
                top_k=20,
                max_output_tokens=max_output_tokens,
            )
            model = genai.GenerativeModel(f"models/{self.model_name}", generation_config=generation_config)
            response = model.generate_content(prompt)
            
            # Some SDK versions put content in response.text, others in response.candidates[0].content.parts[0].text
            text = getattr(response, "text", None)
            if not text and hasattr(response, "candidates"):
                text = response.candidates[0].content.parts[0].text
                
            return text or ""
            
        except Exception as e:
            logger.error(f"❌ Error generating content: {e}")
            return ""
