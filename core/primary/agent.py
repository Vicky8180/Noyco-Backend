# core/primary/agent.py
import time
import logging
from typing import Dict, List, Optional, Any
from functools import lru_cache
from common.gemini_client import get_gemini_client
from common.models import Checkpoint

# Configure logging for performance tracking
logger = logging.getLogger(__name__)

class PerformanceTracker:
    """Track performance of different code sections"""
    
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.start_time = None
        
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.perf_counter() - self.start_time
        logger.info(f"⏱️ {self.operation_name}: {duration*1000:.2f}ms")
        print(f"⏱️ {self.operation_name}: {duration*1000:.2f}ms")  # Also print to console


class ConversationAnalyzer:
    """Analyzes conversation context for checkpoint-oriented responses"""
    
    @staticmethod
    def analyze_conversation_stage(context: List[Dict[str, str]], checkpoint: Optional[Checkpoint]) -> Dict[str, str]:
        """Determine conversation stage with checkpoint focus"""
        with PerformanceTracker("ConversationAnalyzer.analyze_conversation_stage"):
            if not context:
                return {"stage": "initial", "tone": "welcoming"}

            # Check last 2 messages for efficiency
            recent_messages = context[-2:]
            user_messages = [msg["content"].lower() for msg in recent_messages if msg.get("role") == "user"]
            
            if not user_messages:
                return {"stage": "general", "tone": "supportive"}
                
            last_message = user_messages[-1]
            
            # Check for questions
            has_questions = "?" in last_message or any(q in last_message for q in ['what', 'how', 'why', 'should', 'can', 'is'])
            
            if has_questions:
                return {"stage": "patient_questions", "tone": "explanatory"}
            elif checkpoint:
                return {"stage": "checkpoint", "tone": "guiding"}
            else:
                return {"stage": "general", "tone": "supportive"}

    @staticmethod
    def extract_user_questions(text: str) -> List[str]:
        """Extract questions from user message"""
        with PerformanceTracker("ConversationAnalyzer.extract_user_questions"):
            if '?' not in text:
                return []
                
            # Split on sentences and find questions
            sentences = [s.strip() for s in text.replace('?', '?|').split('|') if s.strip()]
            questions = [s for s in sentences if '?' in s]
            
            return questions[:2]  # Limit to 2 questions


class CheckpointManager:
    """Handles checkpoint-specific logic efficiently"""
    
    @staticmethod
    def extract_inputs_from_text(text: str, checkpoint: Optional[Checkpoint]) -> Dict[str, Any]:
        """Extract relevant inputs from user text based on checkpoint"""
        with PerformanceTracker("CheckpointManager.extract_inputs_from_text"):
            if not checkpoint or not hasattr(checkpoint, 'expected_inputs') or not checkpoint.expected_inputs:
                return {}
            
            collected = {}
            text_lower = text.lower()
            
            # Enhanced pattern matching for medical inputs
            for field in checkpoint.expected_inputs:
                field_lower = field.lower()
                
                # More comprehensive pattern matching
                if any(word in field_lower for word in ['pain', 'hurt', 'ache']) and any(word in text_lower for word in ['pain', 'hurt', 'ache', 'sore', 'tender']):
                    collected[field] = text[:150]
                elif any(word in field_lower for word in ['symptom', 'feel']) and any(word in text_lower for word in ['feel', 'symptom', 'experience', 'having', 'suffering']):
                    collected[field] = text[:150]
                elif any(word in field_lower for word in ['duration', 'time', 'when']) and any(word in text_lower for word in ['since', 'days', 'weeks', 'months', 'ago', 'started']):
                    collected[field] = text[:150]
                elif any(word in field_lower for word in ['medication', 'medicine', 'drug']) and any(word in text_lower for word in ['taking', 'medication', 'medicine', 'pill', 'drug', 'prescribed']):
                    collected[field] = text[:150]
                elif any(word in field_lower for word in ['compliance', 'taking']) and any(word in text_lower for word in ['taking', 'yes', 'no', 'regularly', 'sometimes', 'forgot']):
                    collected[field] = text[:150]
                elif any(word in field_lower for word in ['side', 'effect', 'reaction']) and any(word in text_lower for word in ['side', 'effect', 'reaction', 'nausea', 'upset', 'dizzy']):
                    collected[field] = text[:150]
                elif any(word in field_lower for word in ['frequency', 'often']) and any(word in text_lower for word in ['often', 'sometimes', 'always', 'rarely', 'frequency']):
                    collected[field] = text[:150]
                elif any(word in field_lower for word in ['hydration', 'fluid', 'water']) and any(word in text_lower for word in ['water', 'fluid', 'drink', 'hydrated']):
                    collected[field] = text[:150]
            
            return collected

    @staticmethod
    def calculate_checkpoint_status(checkpoint: Optional[Checkpoint], collected_inputs: Dict[str, Any], current_status: str) -> str:
        """Calculate new checkpoint status based on collected inputs"""
        with PerformanceTracker("CheckpointManager.calculate_checkpoint_status"):
            if not checkpoint or not hasattr(checkpoint, 'expected_inputs') or not checkpoint.expected_inputs:
                return current_status
            
            expected_fields = checkpoint.expected_inputs
            completed_fields = [f for f in expected_fields if f in collected_inputs and collected_inputs[f]]
            
            if not completed_fields:
                return "pending"
            
            completion_rate = len(completed_fields) / len(expected_fields)
            
            if completion_rate >= 0.7:  # 70% completion threshold
                return "complete"
            elif completion_rate >= 0.3:  # 30% to start progress
                return "in_progress"
            else:
                return "pending"


class BalancedResponseBuilder:
    """Balanced response builder - good performance with complete functionality"""

    @staticmethod
    @lru_cache(maxsize=16)
    def get_stage_guidance(stage: str, has_checkpoint: bool, is_final: bool) -> str:
        """Cached stage guidance for better performance"""
        if stage == "patient_questions":
            return "FOCUS: Answer their questions clearly and provide reassuring explanations."
        elif stage == "checkpoint" and has_checkpoint:
            return "FOCUS: Address their input and guide through checkpoint completion if needed."
        elif is_final:
            return "FOCUS: Provide comprehensive summary and next steps."
        else:
            return "FOCUS: Provide supportive, helpful responses addressing their concerns."

    @staticmethod
    def build_checkpoint_context(checkpoint: Optional[Checkpoint], collected_inputs: Dict[str, Any], is_final: bool) -> str:
        """Build focused checkpoint context"""
        with PerformanceTracker("BalancedResponseBuilder.build_checkpoint_context"):
            if not checkpoint:
                return ""

            context_parts = [f"📍 Current Assessment: {checkpoint.name}"]

            if hasattr(checkpoint, 'expected_inputs') and checkpoint.expected_inputs:
                expected = checkpoint.expected_inputs
                collected = [f for f in expected if f in collected_inputs and collected_inputs[f]]
                missing = [f for f in expected if f not in collected or not collected_inputs[f]]
                
                context_parts.append(f"Progress: {len(collected)}/{len(expected)} completed")
                
                if collected:
                    context_parts.append(f"✅ Information received: {', '.join(collected[:3])}")
                
                if missing and len(missing) <= 3:
                    context_parts.append(f"⏳ Still need to discuss: {', '.join(missing)}")

            if is_final:
                context_parts.append("🎯 This is the final assessment step")

            return "\n".join(context_parts)

    @staticmethod
    def build_conversation_context(context: List[Dict[str, str]]) -> str:
        """Build minimal but useful conversation context"""
        with PerformanceTracker("BalancedResponseBuilder.build_conversation_context"):
            if not context:
                return ""

            # Only last 3 exchanges for context
            recent = context[-6:]  # 3 back-and-forth exchanges
            formatted = []
            
            for turn in recent:
                role = turn.get("role")
                content = turn.get("content", "")
                
                if not content:
                    continue
                    
                if role == "user":
                    formatted.append(f"Patient: {content}")
                elif role == "assistant":
                    # Keep it concise
                    if len(content) > 80:
                        content = content[:77] + "..."
                    formatted.append(f"Khusbu: {content}")

            return "\n".join(formatted[-4:])  # Last 4 lines only

    @staticmethod
    def build_comprehensive_prompt(text: str, context: List[Dict[str, str]], checkpoint: Optional[Checkpoint],
                                 collected_inputs: Dict[str, Any], is_final: bool) -> str:
        """Build comprehensive but efficient prompt"""
        with PerformanceTracker("BalancedResponseBuilder.build_comprehensive_prompt"):
            
            # Analyze conversation
            conv_analysis = ConversationAnalyzer.analyze_conversation_stage(context, checkpoint)
            user_questions = ConversationAnalyzer.extract_user_questions(text)

            prompt_parts = [
                """You are Khusbu, an experienced and caring nurse providing patient care and support.

Your approach:
- Always acknowledge their concerns or questions first
- Provide clear, helpful responses in natural conversation style
- Use warm, professional but friendly tone
- Give practical guidance when appropriate
- If doing an assessment, gently guide them through it while addressing their immediate concerns"""
            ]

            # Add stage-specific guidance
            stage_guidance = BalancedResponseBuilder.get_stage_guidance(
                conv_analysis["stage"], checkpoint is not None, is_final)
            prompt_parts.append(stage_guidance)

            # Add conversation context if meaningful
            conv_context = BalancedResponseBuilder.build_conversation_context(context)
            if conv_context:
                prompt_parts.append(f"Recent conversation:\n{conv_context}")

            # Add checkpoint information
            if checkpoint:
                checkpoint_context = BalancedResponseBuilder.build_checkpoint_context(
                    checkpoint, collected_inputs, is_final)
                if checkpoint_context:
                    prompt_parts.append(checkpoint_context)

            # Add current message
            prompt_parts.append(f'Patient says: "{text}"')

            # Add specific instructions based on context
            instructions = []
            
            if user_questions:
                instructions.append(f"- Answer their specific questions: {'; '.join(user_questions)}")
            
            if checkpoint and hasattr(checkpoint, 'expected_inputs') and checkpoint.expected_inputs:
                expected = checkpoint.expected_inputs
                missing = [f for f in expected if f not in collected_inputs or not collected_inputs[f]]
                if missing:
                    instructions.append(f"- If natural, gently ask about: {', '.join(missing[:2])}")
            
            if is_final:
                instructions.append("- Provide a helpful summary and suggest next steps")
            
            if instructions:
                prompt_parts.append("Instructions:\n" + "\n".join(instructions))

            prompt_parts.append("""
Respond naturally and helpfully. Keep responses conversational but informative (3-5 sentences typically).""")

            return "\n\n".join(prompt_parts)


async def process_message(
    text: str,
    conversation_id: str,
    task_id: Optional[str],
    checkpoint: Optional[Checkpoint],
    context: List[Dict[str, str]],
    checkpoint_status: str = "pending",
    sync_agent_results: Optional[Any] = None,  # Kept for compatibility
    async_agent_results: Optional[Any] = None,  # Kept for compatibility
    task_stack: Optional[List[Dict[str, Any]]] = None,
    is_last_checkpoint: bool = False
) -> Dict[str, Any]:
    """
    Balanced message processing - good performance with complete functionality
    """
    
    # Track total execution time
    total_start_time = time.perf_counter()
    
    print(f"🚀 Starting process_message for: '{text[:50]}...'")
    
    # Extract inputs from user message
    collected_inputs = CheckpointManager.extract_inputs_from_text(text, checkpoint)
    
    # Build comprehensive prompt
    prompt = BalancedResponseBuilder.build_comprehensive_prompt(
        text, context, checkpoint, collected_inputs, is_last_checkpoint)

    print(f"📝 Prompt length: {len(prompt)} characters")

    # Generate response with balanced settings
    try:
        with PerformanceTracker("get_gemini_client"):
            client = get_gemini_client()
          
        with PerformanceTracker("gemini_generate_content"):
            response = await client.generate_content(
        prompt,
        generation_config={
            "temperature": 0.6,      # Slightly lower for consistency
            "top_p": 0.85,           # Optimized for speed
            "max_output_tokens": 200,  # Reduced from 300 - major speed boost
            "candidate_count": 1
        }
    )
        
        with PerformanceTracker("response_processing"):
            response_text = response.text.strip()

            # Ensure minimum response quality
            if len(response_text) < 25:
                if checkpoint:
                    response_text = f"I understand your concern about {text}. Let me help you with {checkpoint.name}. Could you share a bit more detail?"
                else:
                    response_text = "I understand what you're sharing. Could you tell me a bit more so I can better help and support you?"

    except Exception as e:
        with PerformanceTracker("exception_handling"):
            print(f"❌ Error in gemini_generate_content: {str(e)}")
            # Contextual fallback responses
            if checkpoint:
                response_text = f"I'm here to help you with {checkpoint.name}. Could you share more details about what you're experiencing?"
            else:
                response_text = "I'm here to support you. Please tell me more about what's concerning you so I can help."

    # Calculate new checkpoint status
    new_checkpoint_status = CheckpointManager.calculate_checkpoint_status(
        checkpoint, collected_inputs, checkpoint_status)

    # Enhanced quality metrics
    with PerformanceTracker("quality_metrics_calculation"):
        response_quality = {
            "overall_score": 0.8 if len(response_text) > 30 else 0.6,
            "has_empathy": any(word in response_text.lower() for word in ['understand', 'care', 'support', 'help', 'concern']),
            "appropriate_length": 30 <= len(response_text) <= 400,
            "uses_clinical_context": checkpoint is not None and checkpoint.name.lower() in response_text.lower()
        }

    conversation_stage = ConversationAnalyzer.analyze_conversation_stage(context, checkpoint)

    with PerformanceTracker("response_dict_creation"):
        result = {
            "response": response_text,
            "checkpoint_status": new_checkpoint_status,
            "requires_human": False,
            "human_intervention_reason": "",
            "collected_inputs": collected_inputs,
            "action_required": False,
            "has_critical_alerts": False,
            "clinical_insights_available": 0,
            "medication_info_available": 0,
            "confidence_level": "medium",
            "response_quality": response_quality,
            "conversation_stage": conversation_stage,
            "is_final_summary": is_last_checkpoint and new_checkpoint_status == "complete"
        }

    # Log total execution time
    total_duration = time.perf_counter() - total_start_time
    print(f"⏱️ 🎯 TOTAL EXECUTION TIME: {total_duration*1000:.2f}ms")
    logger.info(f"⏱️ 🎯 TOTAL EXECUTION TIME: {total_duration*1000:.2f}ms")
    
    return result
