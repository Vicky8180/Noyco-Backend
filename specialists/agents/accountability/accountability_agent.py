"""
Accountability Buddy Agent for Life Reboots
Main agent implementation for goal tracking, daily check-ins, and encouragement
Uses two-collection architecture similar to therapy agent
"""

import logging
import uuid
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, date, time
import re
import json

# Import memory clients
from memory.mongo_client import MongoMemory
from memory.redis_client import RedisMemory

# Import local modules
from .database_manager import AccountabilityDatabaseManager
from .redis_manager import AccountabilityRedis
from .response_generator import AccountabilityResponseGenerator
from .llm_service import AccountabilityLLMService
from .schema import (
    AccountabilityRequest, AccountabilityResponse, AccountabilityGoal, DailyCheckIn, 
    CheckInResponse, GoalCategory, GoalStatus, CheckInType, ResponseType, ProgressLevel,
    GoalMetric, CheckpointState, GOAL_TEMPLATES
)

# Import common models
from common.models import AgentResult

logger = logging.getLogger(__name__)

class AccountabilityBuddyAgent:
    """Main accountability buddy agent for life reboot support using two-collection architecture"""
    
    def __init__(self):
        # Database managers
        self.db_manager = AccountabilityDatabaseManager()
        self.redis = AccountabilityRedis()
        self.response_generator = AccountabilityResponseGenerator()
        self.llm_service = AccountabilityLLMService()
        
        # Main memory systems (for integration)
        self.mongo_memory = MongoMemory()
        self.redis_memory = RedisMemory()
        
        self.initialized = False
        
    async def initialize(self):
        """Initialize all connections and services"""
        try:
            # Initialize database connections
            await self.db_manager.initialize()
            await self.redis.initialize()
            
            # Initialize LLM service
            await self.llm_service.initialize()
            
            # Initialize main memory systems
            await self.mongo_memory.initialize()
            await self.redis_memory.check_connection()
            
            self.initialized = True
            logger.info("✅ Accountability Buddy Agent initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Accountability Agent: {e}")
            raise
            
    async def process_message(self, request: AccountabilityRequest) -> AgentResult:
        """Process incoming message using new two-collection architecture"""
        try:
            if not self.initialized:
                await self.initialize()
                
            logger.info(f"🎯 Processing accountability request from user {request.user_profile_id}")
            
            # Ensure agent instance exists
            agent_instance = await self.db_manager.ensure_agent_instance(
                request.agent_instance_id, 
                request.user_profile_id,
                request.individual_id
            )
            
            # Analyze user intent using LLM
            intent_result = await self.llm_service.analyze_intent(request.text, request.context)
            logger.info(f"🧠 Detected intent: {intent_result.get('intent')} (confidence: {intent_result.get('confidence', 0)})")
            
            # Process based on detected intent
            response_data = await self._process_intent(intent_result, request, agent_instance)
            
            # Update last interaction and checkpoint
            await self.db_manager.update_agent_instance(request.agent_instance_id, {
                "last_interaction": datetime.utcnow().isoformat(),
                "last_checkpoint": response_data.get("checkpoint", CheckpointState.GREETING),
                "total_conversations": agent_instance.get("total_conversations", 0) + 1
            })
            
            # Log conversation
            await self.db_manager.log_conversation(
                user_profile_id=request.user_profile_id,
                agent_instance_id=request.agent_instance_id,
                conversation_id=request.conversation_id,
                text=request.text,
                checkpoint=response_data.get("checkpoint"),
                context=request.context,
                goal_updates=response_data.get("goal_updates", []),
                checkin_completed=response_data.get("checkin_completed", False)
            )
            
            return AgentResult(
                agent_name="Accountability Buddy",
                status="success",
                result_payload=response_data,
                message_to_user=response_data.get("reply", "I'm here to support your goals!"),
                action_required=response_data.get("action_required", False),
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"❌ Error processing accountability message: {e}")
            return AgentResult(
                agent_name="Accountability Buddy",
                status="error",
                result_payload={"error": str(e)},
                message_to_user="I'm having trouble right now, but I'm here to support you. Please try again.",
                action_required=False,
                timestamp=datetime.utcnow()
            )
    
    async def _process_intent(self, intent_result: Dict[str, Any], request: AccountabilityRequest, agent_instance: Dict[str, Any]) -> Dict[str, Any]:
        """Process user message based on detected intent"""
        intent = intent_result.get("intent", "general_conversation")
        extracted_data = intent_result.get("extracted_data", {})
        
        try:
            if intent == "goal_creation":
                return await self._handle_goal_creation(request, agent_instance, extracted_data)
            elif intent == "daily_checkin":
                return await self._handle_daily_checkin(request, agent_instance)
            elif intent == "rating_response":
                rating = extracted_data.get("rating", 5)
                return await self._handle_rating_response(request, agent_instance, rating)
            elif intent == "yes_no_response":
                answer = extracted_data.get("answer", True)
                return await self._handle_yes_no_response(request, agent_instance, answer)
            elif intent == "progress_review":
                return await self._handle_progress_review(request, agent_instance)
            elif intent == "motivation_request":
                return await self._handle_motivation_request(request, agent_instance)
            elif intent == "goal_modification":
                return await self._handle_goal_modification(request, agent_instance)
            else:
                return await self._handle_general_conversation(request, agent_instance)
                
        except Exception as e:
            logger.error(f"❌ Error processing intent {intent}: {e}")
            return {
                "reply": "I'm here to help with your accountability goals! What would you like to work on?",
                "checkpoint": CheckpointState.GREETING,
                "context": request.context,
                "action_required": False
            }
            
    async def _handle_goal_creation(self, request: AccountabilityRequest, agent_instance: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle goal creation with LLM assistance"""
        try:
            # Extract detailed goal information using LLM
            goal_details = await self.llm_service.extract_goal_details(request.text)
            
            # Map to our goal categories
            category_map = {
                "fitness": GoalCategory.HEALTH_FITNESS,
                "sobriety": GoalCategory.SOBRIETY,
                "meditation": GoalCategory.MEDITATION,
                "therapy": GoalCategory.THERAPY,
                "habits": GoalCategory.HABITS,
                "career": GoalCategory.CAREER,
                "relationships": GoalCategory.RELATIONSHIPS,
                "mental_health": GoalCategory.MENTAL_HEALTH
            }
            
            goal_category = category_map.get(goal_details.get("goal_category", "other"), GoalCategory.OTHER)
            
            # Create goal with extracted details
            goal = AccountabilityGoal(
                goal_id=str(uuid.uuid4()),
                user_profile_id=request.user_profile_id,
                title=goal_details.get("goal_title", "Personal Goal"),
                description=goal_details.get("goal_description", request.text),
                category=goal_category,
                motivation=goal_details.get("motivation", ""),
                metrics=[GoalMetric(
                    name="daily_progress",
                    type=ResponseType.RATING,
                    question=f"How did you do with '{goal_details.get('goal_title', 'your goal')}' today? (1-10)",
                    target_value=7.0
                )]
            )
            
            # Save goal to database
            success = await self.db_manager.create_goal(request.agent_instance_id, goal)
            
            if success:
                # Generate personalized response using LLM
                reply = await self.llm_service.generate_goal_response(
                    request.text, 
                    True, 
                    {"title": goal.title, "category": goal.category.value, "description": goal.description}
                )
                
                return {
                    "reply": reply,
                    "checkpoint": CheckpointState.GOAL_CREATION,
                    "context": request.context,
                    "goal_created": True,
                    "goal_id": goal.goal_id,
                    "goal_updates": [goal.goal_id],
                    "action_required": False
                }
            else:
                reply = await self.llm_service.generate_goal_response(request.text, False)
                return {
                    "reply": reply,
                    "checkpoint": CheckpointState.GREETING,
                    "context": request.context,
                    "goal_created": False,
                    "action_required": False
                }
                
        except Exception as e:
            logger.error(f"❌ Error in goal creation: {e}")
            return {
                "reply": "I'm excited to help you create a goal! What would you like to work on?",
                "checkpoint": CheckpointState.GREETING,
                "context": request.context,
                "goal_created": False,
                "action_required": False
            }
    
    async def _handle_daily_checkin(self, request: AccountabilityRequest, agent_instance: Dict[str, Any]) -> Dict[str, Any]:
        """Handle daily check-in process"""
        try:
            # Get user's active goals
            goals = await self.db_manager.get_user_goals(request.agent_instance_id, GoalStatus.ACTIVE)
            
            if not goals:
                return {
                    "reply": "I'd love to help you check in! First, let's create a goal to track. What would you like to work on? 🎯",
                    "checkpoint": CheckpointState.GOAL_CREATION,
                    "context": request.context,
                    "checkin_completed": False,
                    "action_required": True
                }
                
            # Generate personalized check-in prompt
            goal_titles = [g["title"] for g in goals[:3]]  # Show up to 3 goals
            goal_list = ", ".join(goal_titles)
            
            reply = f"Great! Let's check in on your goals: {goal_list}. How did you do today? You can rate yourself 1-10 or just tell me yes/no! 📊"
            
            return {
                "reply": reply,
                "checkpoint": CheckpointState.DAILY_CHECKIN,
                "context": {**request.context, "active_goals": [g["goal_id"] for g in goals]},
                "checkin_completed": False,
                "action_required": True
            }
            
        except Exception as e:
            logger.error(f"❌ Error in daily check-in: {e}")
            return {
                "reply": "I'm here for your check-in! How are you doing with your goals today? 😊",
                "checkpoint": CheckpointState.DAILY_CHECKIN,
                "context": request.context,
                "checkin_completed": False,
                "action_required": False
                }
                
    async def _handle_rating_response(self, request: AccountabilityRequest, agent_instance: Dict[str, Any], rating: int) -> Dict[str, Any]:
        """Handle rating response with LLM-generated feedback"""
        try:
            active_goals = request.context.get("active_goals", [])
            
            if active_goals:
                goal_id = active_goals[0]
                
                # Create check-in record
                checkin = DailyCheckIn(
                    checkin_id=str(uuid.uuid4()),
                    goal_id=goal_id,
                    user_profile_id=request.user_profile_id,
                    conversation_id=request.conversation_id,
                    checkin_type=CheckInType.CUSTOM,
                    responses=[CheckInResponse(
                        metric_name="daily_progress",
                        response_type=ResponseType.RATING,
                        rating_value=rating
                    )],
                    overall_score=float(rating),
                    progress_level=self._get_progress_level(rating)
                )
                
                # Save check-in
                success = await self.db_manager.save_checkin(request.agent_instance_id, checkin)
                
                if success:
                    # Generate intelligent response using LLM
                    reply = await self.llm_service.generate_checkin_response(
                        {"rating": rating, "overall_score": rating},
                        {"goal_id": goal_id},
                        {}  # Could add streak data here
                    )
                
                return {
                        "reply": reply,
                        "checkpoint": CheckpointState.RATING_RESPONSE,
                        "context": request.context,
                        "checkin_completed": True,
                        "overall_score": rating,
                        "goal_updates": [goal_id],
                        "action_required": False
                    }
            
            # Fallback response
            if rating >= 8:
                reply = f"Amazing! A {rating}/10 is fantastic! You're doing incredible work! 🌟"
            elif rating >= 6:
                reply = f"Great job! A {rating}/10 shows solid progress! 👏"
            elif rating >= 4:
                reply = f"Thanks for being honest with {rating}/10. Every step counts! 💪"
            else:
                reply = f"I appreciate your honesty. A {rating}/10 means tomorrow is a fresh start! 🌅"
                
            return {
                "reply": reply,
                "checkpoint": CheckpointState.RATING_RESPONSE,
                "context": request.context,
                "checkin_completed": bool(active_goals),
                "overall_score": rating,
                "action_required": False
            }
            
        except Exception as e:
            logger.error(f"❌ Error handling rating response: {e}")
            return {
                "reply": f"Thanks for sharing that {rating}/10! Every honest check-in helps! 😊",
                "checkpoint": CheckpointState.RATING_RESPONSE,
                "context": request.context,
                "action_required": False
            }
    
    async def _handle_yes_no_response(self, request: AccountabilityRequest, agent_instance: Dict[str, Any], answer: bool) -> Dict[str, Any]:
        """Handle yes/no response"""
        try:
            active_goals = request.context.get("active_goals", [])
            
            if active_goals:
                goal_id = active_goals[0]
                score = 8.0 if answer else 3.0
                
                checkin = DailyCheckIn(
                    checkin_id=str(uuid.uuid4()),
                    goal_id=goal_id,
                    user_profile_id=request.user_profile_id,
                    conversation_id=request.conversation_id,
                    checkin_type=CheckInType.CUSTOM,
                    responses=[CheckInResponse(
                        metric_name="daily_success",
                response_type=ResponseType.YES_NO,
                        yes_no_value=answer
                    )],
                    overall_score=score,
                    progress_level=self._get_progress_level(int(score))
                )
                
                success = await self.db_manager.save_checkin(request.agent_instance_id, checkin)
                
                if success:
                    # Generate response using LLM
                    reply = await self.llm_service.generate_checkin_response(
                        {"answer": answer, "overall_score": score}
                    )
                    
                    return {
                        "reply": reply,
                        "checkpoint": CheckpointState.YES_NO_RESPONSE,
                        "context": request.context,
                        "checkin_completed": True,
                        "overall_score": score,
                        "goal_updates": [goal_id],
                        "action_required": False
                    }
            
            # Fallback response
            if answer:
                reply = "That's wonderful to hear! You're doing great! 🌟"
            else:
                reply = "I appreciate your honesty. Every day is a new chance to grow! 🌱"
            
            return {
                "reply": reply,
                "checkpoint": CheckpointState.YES_NO_RESPONSE,
                "context": request.context,
                "checkin_completed": bool(active_goals),
                "action_required": False
            }
            
        except Exception as e:
            logger.error(f"❌ Error handling yes/no response: {e}")
            return {
                "reply": "Thanks for sharing! I'm here to support you! 😊",
                "checkpoint": CheckpointState.YES_NO_RESPONSE,
                "context": request.context,
                "action_required": False
            }
            
    async def _handle_progress_review(self, request: AccountabilityRequest, agent_instance: Dict[str, Any]) -> Dict[str, Any]:
        """Handle progress review request"""
        try:
            # Get user summary
            summary = await self.db_manager.get_user_summary(request.agent_instance_id)
            
            if summary:
                goals_count = summary.get("active_goals", 0)
                success_rate = summary.get("success_rate", 0)
                total_checkins = summary.get("total_checkins", 0)
                current_streaks = summary.get("current_streaks", {})
                
                if goals_count == 0:
                    reply = "You haven't created any goals yet! Let's start your accountability journey. What would you like to work on?"
                elif total_checkins == 0:
                    reply = f"You have {goals_count} active goal{'s' if goals_count != 1 else ''}! Ready for your first check-in?"
                else:
                    streak_text = ""
                    if current_streaks:
                        max_streak = max(current_streaks.values())
                        if max_streak > 0:
                            streak_text = f" Your best current streak is {max_streak} days!"
                    
                    reply = f"You're doing amazing! You have {goals_count} active goal{'s' if goals_count != 1 else ''} with a {success_rate}% success rate over {total_checkins} check-ins.{streak_text} Keep up the incredible work! 🌟"
            else:
                reply = "Let's start tracking your progress! What goal would you like to work on?"
            
            return {
                "reply": reply,
                "checkpoint": CheckpointState.PROGRESS_REVIEW,
                "context": request.context,
                "progress_data": summary,
                "action_required": False
            }
            
        except Exception as e:
            logger.error(f"❌ Error handling progress review: {e}")
            return {
                "reply": "You're making progress every day, even when it doesn't feel like it! Keep going! 💪",
                "checkpoint": CheckpointState.PROGRESS_REVIEW,
                "context": request.context,
                "action_required": False
            }
            
    async def _handle_motivation_request(self, request: AccountabilityRequest, agent_instance: Dict[str, Any]) -> Dict[str, Any]:
        """Handle motivation/support request"""
        try:
            # Generate personalized motivation using LLM
            user_context = {
                "total_goals": len(agent_instance.get("goals", [])),
                "total_checkins": agent_instance.get("total_checkins", 0),
                "recent_interaction": agent_instance.get("last_interaction"),
                "user_text": request.text
            }
            
            reply = await self.llm_service.generate_motivation_message(user_context)
                
            return {
                "reply": reply,
                "checkpoint": CheckpointState.MOTIVATION_REQUEST,
                "context": request.context,
                "action_required": False
            }
            
        except Exception as e:
            logger.error(f"❌ Error handling motivation request: {e}")
            return {
                "reply": "💪 You're stronger than you know! Every day you show up is a victory!",
                "checkpoint": CheckpointState.MOTIVATION_REQUEST,
                "context": request.context,
                "action_required": False
            }
            
    async def _handle_goal_modification(self, request: AccountabilityRequest, agent_instance: Dict[str, Any]) -> Dict[str, Any]:
        """Handle goal modification requests"""
        return {
            "reply": "I'd love to help you adjust your goals! What changes would you like to make?",
            "checkpoint": CheckpointState.GOAL_MODIFICATION,
            "context": request.context,
                    "action_required": True
                }
                
    async def _handle_general_conversation(self, request: AccountabilityRequest, agent_instance: Dict[str, Any]) -> Dict[str, Any]:
        """Handle general conversation"""
        greetings = [
            "Hi there! I'm your Accountability Buddy, here to support your goals and celebrate your progress! 🎯",
            "Hello! Ready to work on your goals together? I'm here to cheer you on! 🌟",
            "Hey! I'm excited to be part of your accountability journey. What can we work on today? 💪"
        ]
        
        import random
        reply = random.choice(greetings)
            
        return {
            "reply": reply,
            "checkpoint": CheckpointState.GREETING,
            "context": request.context,
            "action_required": False
        }
    
    def _get_progress_level(self, score: int) -> ProgressLevel:
        """Convert numeric score to progress level"""
        if score >= 9:
            return ProgressLevel.EXCELLENT
        elif score >= 7:
            return ProgressLevel.GOOD
        elif score >= 5:
            return ProgressLevel.FAIR
        elif score >= 3:
            return ProgressLevel.STRUGGLING
        else:
            return ProgressLevel.DIFFICULT

# === MAIN PROCESS FUNCTION ===

async def process_message(
    text: str,
    conversation_id: str,
    user_profile_id: str,
    agent_instance_id: str,
    checkpoint: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    individual_id: Optional[str] = None,
) -> AgentResult:
    """Main entry point for processing accountability agent messages"""
    try:
        request = AccountabilityRequest(
            text=text,
            conversation_id=conversation_id,
        checkpoint=checkpoint,
            context=context or {},
            individual_id=individual_id,
            user_profile_id=user_profile_id,
            agent_instance_id=agent_instance_id
        )
        
        agent = AccountabilityBuddyAgent()
        result = await agent.process_message(request)
        return result
        
    except Exception as e:
        logger.error(f"❌ Error in accountability process_message: {e}")
        return AgentResult(
            agent_name="Accountability Buddy",
            status="error",
            result_payload={"error": str(e)},
            message_to_user="I'm having some trouble right now, but I'm still here to support your goals!",
            action_required=False,
            timestamp=datetime.utcnow()
        )
