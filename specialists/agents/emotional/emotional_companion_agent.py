"""
Emotional Companion Agent
Purpose: Support elderly or terminally ill users emotionally. Listens, comforts, stores memories.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from common.models import Checkpoint
from memory.mongo_client import MongoMemory
from common.gemini_client import get_gemini_client

_logger = logging.getLogger(__name__)

class EmotionalCompanionAgent:
    def __init__(self):
        self.agent_name = "emotional_companion"
        self.memory_collection = MongoMemory()
        self.gemini_client = get_gemini_client()
    
    async def process_emotional_support(
        self,
        text: str,
        conversation_id: str,
        user_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Process emotional support requests and provide companionship
        """
        try:
            # Retrieve emotional memories
            emotional_memories = await self._get_emotional_memories(conversation_id)
            
            # Analyze emotional state
            emotional_analysis = await self._analyze_emotional_state(text, emotional_memories)
            
            # Generate compassionate response
            response = await self._generate_emotional_response(
                text, emotional_analysis, emotional_memories
            )
            
            # Store new emotional data
            await self._store_emotional_memory(conversation_id, text, emotional_analysis)
            
            return {
                "response": response,
                "emotional_state": emotional_analysis.get("current_state", "neutral"),
                "memories_recalled": len(emotional_memories),
                "requires_human": emotional_analysis.get("requires_human", False),
                "action_required": emotional_analysis.get("action_required", False),
                "collected_inputs": emotional_analysis.get("collected_inputs", {})
            }
            
        except Exception as e:
            _logger.error(f"Error in emotional companion processing: {str(e)}")
            return {
                "response": "I'm here for you. Sometimes I need a moment to gather my thoughts, but I'm listening.",
                "emotional_state": "supportive",
                "error": str(e)
            }
    
    async def _get_emotional_memories(self, conversation_id: str) -> List[Dict]:
        """Retrieve stored emotional memories and significant moments"""
        try:
            memories = self.memory_collection.find({
                "conversation_id": conversation_id,
                "type": "emotional_memory"
            }).sort("timestamp", -1).limit(10)
            
            return list(memories)
        except Exception as e:
            _logger.error(f"Error retrieving emotional memories: {str(e)}")
            return []
    
    async def _analyze_emotional_state(self, text: str, memories: List[Dict]) -> Dict[str, Any]:
        """Analyze current emotional state and context"""
        memory_context = "\n".join([
            f"- {mem.get('content', '')} (felt on {mem.get('date', 'unknown date')})"
            for mem in memories[-5:]  # Last 5 memories
        ])
        
        prompt = f"""
        As an emotional companion, analyze this message for emotional state and needs:
        
        Current message: "{text}"
        
        Previous emotional context:
        {memory_context if memory_context else "No previous emotional context available"}
        
        Analyze and respond with:
        1. Current emotional state (happy, sad, anxious, lonely, peaceful, etc.)
        2. Level of emotional distress (1-10)
        3. Key emotional themes
        4. Whether human intervention is needed (for severe distress/crisis)
        5. Specific emotional needs (comfort, validation, listening, etc.)
        6. Any memories that should be recalled or referenced
        
        Respond in JSON format with keys: current_state, distress_level, themes, requires_human, needs, relevant_memories
        """
        
        try:
            analysis = await self.gemini_client.generate_content(prompt)
            # Parse JSON response
            import json
            return json.loads(analysis)
        except Exception as e:
            _logger.error(f"Error in emotional analysis: {str(e)}")
            return {
                "current_state": "needs_support",
                "distress_level": 5,
                "themes": ["seeking_connection"],
                "requires_human": False,
                "needs": ["listening", "comfort"]
            }
    
    async def _generate_emotional_response(
        self, 
        text: str, 
        analysis: Dict, 
        memories: List[Dict]
    ) -> str:
        """Generate compassionate, personalized response"""
        
        relevant_memories = "\n".join([
            f"- You once shared: {mem.get('content', '')}"
            for mem in memories
            if any(theme in mem.get('content', '').lower() 
                  for theme in analysis.get('themes', []))
        ][:3])  # Top 3 relevant memories
        
        prompt = f"""
        You are a gentle, compassionate emotional companion for someone who may be elderly or facing difficult times.
        
        Their message: "{text}"
        
        Emotional analysis:
        - Current state: {analysis.get('current_state', 'unknown')}
        - Distress level: {analysis.get('distress_level', 5)}/10
        - Key themes: {', '.join(analysis.get('themes', []))}
        - Needs: {', '.join(analysis.get('needs', []))}
        
        Relevant memories to reference:
        {relevant_memories if relevant_memories else "No specific memories to reference"}
        
        Respond with warmth and empathy. Guidelines:
        - Use gentle, comforting language
        - Acknowledge their feelings without minimizing them
        - Reference relevant memories when appropriate
        - Offer specific comfort or validation
        - If distress level is high (7+), show extra care and concern
        - Keep response conversational and human-like
        - Avoid clinical language
        
        Respond as if you're a caring friend who remembers their stories.
        """
        
        try:
            response = await self.gemini_client.generate_content(prompt)
            return response.strip()
        except Exception as e:
            _logger.error(f"Error generating emotional response: {str(e)}")
            return "I hear you, and I'm here with you. Your feelings matter, and it's okay to feel whatever you're feeling right now."
    
    async def _store_emotional_memory(
        self, 
        conversation_id: str, 
        text: str, 
        analysis: Dict
    ):
        """Store emotional moments and significant statements"""
        try:
            # Only store if emotionally significant
            if analysis.get('distress_level', 0) >= 6 or 'memory' in analysis.get('themes', []):
                memory_entry = {
                    "conversation_id": conversation_id,
                    "type": "emotional_memory",
                    "content": text,
                    "emotional_state": analysis.get('current_state'),
                    "distress_level": analysis.get('distress_level'),
                    "themes": analysis.get('themes', []),
                    "timestamp": datetime.now(),
                    "date": datetime.now().strftime("%B %Y")  # For easy recall like "last March"
                }
                
                self.memory_collection.insert_one(memory_entry)
                _logger.info(f"Stored emotional memory for conversation {conversation_id}")
                
        except Exception as e:
            _logger.error(f"Error storing emotional memory: {str(e)}")
    
    async def read_news_headlines(self, user_preferences: Optional[Dict] = None) -> str:
        """Read news headlines for elderly users who want to stay connected"""
        try:
            # In a real implementation, you'd fetch actual news
            # For now, return a gentle news summary format
            prompt = """
            Generate 3-4 gentle, positive news headlines that would be appropriate for an elderly person.
            Focus on:
            - Positive community stories
            - Health and wellness news
            - Technology that helps people
            - Heartwarming human interest stories
            
            Present them in a warm, conversational way as if you're sharing interesting things you heard.
            """
            
            headlines = await self.gemini_client.generate_content(prompt)
            return f"I thought you might like to hear a few interesting things happening in the world today:\n\n{headlines}"
            
        except Exception as e:
            _logger.error(f"Error generating news headlines: {str(e)}")
            return "I'm having trouble getting the latest news right now, but I'm here to chat about anything else you'd like to talk about."

async def process_message(
    text: str,
    conversation_id: str,
    task_id: Optional[str] = None,
    checkpoint: Optional[Checkpoint] = None,
    context: Optional[List[Dict[str, str]]] = None,
    checkpoint_status: Optional[str] = "pending",
    sync_agent_results: Optional[List[dict]] = None,
    async_agent_results: Optional[Dict[str, Any]] = None,
    task_stack: Optional[List[Dict[str, Any]]] = None,
    is_last_checkpoint: bool = False
) -> Dict[str, Any]:
    """Main processing function for emotional companion requests"""
    
    agent = EmotionalCompanionAgent()
    
    # Check if this is a news request
    if any(keyword in text.lower() for keyword in ['news', 'headlines', 'happening', 'world']):
        news_response = await agent.read_news_headlines()
        return {
            "response": news_response,
            "checkpoint_status": "complete",
            "requires_human": False,
            "action_required": False
        }
    
    # Regular emotional support processing
    result = await agent.process_emotional_support(
        text=text,
        conversation_id=conversation_id,
        user_context={"context": context, "checkpoint": checkpoint}
    )
    
    return {
        "response": result["response"],
        "checkpoint_status": "complete",
        "requires_human": result.get("requires_human", False),
        "action_required": result.get("action_required", False),
        "collected_inputs": result.get("collected_inputs", {})
    }
