from fastapi import HTTPException
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pymongo.database import Database
from pymongo import DESCENDING
from .schema import (
    ConversationsResponseSchema,
    ConversationGroupSchema,
    ConversationInstanceSchema,
    ConversationDetailSchema,
    MessageSchema,
    AgentTypeSchema
)

class ConversationMetricsController:
    def __init__(self, db: Database):
        self.db = db
        self.conversations_collection = db.conversations
        # Agent collections for fetching goal titles
        self.loneliness_agents_collection = db.loneliness_agents
        self.accountability_agents_collection = db.accountability_agents
        self.therapy_agents_collection = db.therapy_agents
        self.social_anxiety_agents_collection = db.social_anxiety_agents
        self.emotional_agents_collection = db.emotional_agents

    async def _get_goal_title(self, agent_instance_id: str, detected_agent: str, individual_id: str) -> Optional[str]:
        """Fetch goal title from appropriate agent collection"""
        try:
            # Map detected agent to collection and goal field
            agent_collections = {
                'loneliness': (self.loneliness_agents_collection, 'loneliness_goals'),
                'accountability': (self.accountability_agents_collection, 'accountability_goals'),
                'mental_therapist': (self.therapy_agents_collection, 'therapy_goals'),
                'anxiety': (self.social_anxiety_agents_collection, 'anxiety_goals'),
                'emotional': (self.emotional_agents_collection, 'emotional_goals')
            }
            
            if detected_agent not in agent_collections:
                return None
                
            collection, goals_field = agent_collections[detected_agent]
            
            # Get user_profile_id from a conversation with this agent_instance_id
            sample_conv = self.conversations_collection.find_one({
                "agent_instance_id": agent_instance_id,
                "individual_id": individual_id
            })
            
            if not sample_conv:
                return None
                
            user_profile_id = sample_conv.get("user_profile_id")
            if not user_profile_id:
                return None
            
            # Find the agent document
            agent_doc = collection.find_one({"user_profile_id": user_profile_id})
            
            if not agent_doc:
                return None
                
            # Find the goal with matching goal_id
            goals = agent_doc.get(goals_field, [])
            for goal in goals:
                if goal.get("goal_id") == agent_instance_id:
                    return goal.get("title")
                    
            return None
            
        except Exception as e:
            # If title lookup fails, return None to fall back to agent_instance_id
            return None

    async def get_available_agent_types(self, individual_id: str) -> List[AgentTypeSchema]:
        """Get all available agent types for a user with conversation counts"""
        try:
            pipeline = [
                {"$match": {"individual_id": individual_id}},
                {"$group": {
                    "_id": "$detected_agent",
                    "count": {"$sum": 1},
                    "last_activity": {"$max": "$updated_at"}
                }},
                {"$sort": {"count": -1}}
            ]
            
            result = list(self.conversations_collection.aggregate(pipeline))
            
            agent_types = []
            for item in result:
                agent_types.append(AgentTypeSchema(
                    agent_type=item["_id"],
                    count=item["count"],
                    last_activity=item.get("last_activity")
                ))
            
            return agent_types
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching agent types: {str(e)}")

    async def get_conversations_by_agent_type(
        self, 
        individual_id: str, 
        agent_type: Optional[str] = None
    ) -> ConversationsResponseSchema:
        """Get conversations grouped by agent_instance_id, optionally filtered by agent type"""
        try:
            # Build match filter
            match_filter = {"individual_id": individual_id}
            if agent_type:
                match_filter["detected_agent"] = agent_type

            # Aggregation pipeline to group conversations by agent_instance_id
            pipeline = [
                {"$match": match_filter},
                {"$sort": {"updated_at": -1}},
                {"$group": {
                    "_id": "$agent_instance_id",
                    "detected_agent": {"$first": "$detected_agent"},
                    "conversations": {
                        "$push": {
                            "conversation_id": "$conversation_id",
                            "agent_instance_id": "$agent_instance_id",
                            "detected_agent": "$detected_agent",
                            "last_message_preview": {
                                "$cond": {
                                    "if": {"$gt": [{"$size": "$context"}, 0]},
                                    "then": {"$arrayElemAt": ["$context.content", -1]},
                                    "else": "No messages"
                                }
                            },
                            "message_count": {"$size": "$context"},
                            "created_at": "$created_at",
                            "updated_at": "$updated_at",
                            "is_active": {"$not": "$is_paused"}
                        }
                    },
                    "conversation_count": {"$sum": 1},
                    "last_activity": {"$max": "$updated_at"},
                    "total_messages": {"$sum": {"$size": "$context"}}
                }},
                {"$sort": {"last_activity": -1}}
            ]

            result = list(self.conversations_collection.aggregate(pipeline))
            
            # Transform result to response schema
            conversation_groups = []
            total_conversations = 0
            total_messages = 0

            for group in result:
                conversations = []
                for conv in group["conversations"]:
                    conversations.append(ConversationInstanceSchema(
                        conversation_id=conv["conversation_id"],
                        agent_instance_id=conv["agent_instance_id"],
                        detected_agent=conv["detected_agent"],
                        last_message_preview=conv["last_message_preview"][:100] + "..." if len(conv["last_message_preview"]) > 100 else conv["last_message_preview"],
                        message_count=conv["message_count"],
                        created_at=conv.get("created_at", datetime.now()),
                        updated_at=conv.get("updated_at"),
                        is_active=conv["is_active"]
                    ))

                # Fetch goal title for this agent_instance_id
                goal_title = await self._get_goal_title(
                    agent_instance_id=group["_id"],
                    detected_agent=group["detected_agent"],
                    individual_id=individual_id
                )

                conversation_groups.append(ConversationGroupSchema(
                    agent_instance_id=group["_id"],
                    detected_agent=group["detected_agent"],
                    goal_title=goal_title,  # Include the goal title
                    conversation_count=group["conversation_count"],
                    conversations=conversations,
                    last_activity=group["last_activity"] or datetime.now(),
                    total_messages=group["total_messages"]
                ))

                total_conversations += group["conversation_count"]
                total_messages += group["total_messages"]

            return ConversationsResponseSchema(
                user_profile_id=individual_id,
                agent_type=agent_type,
                conversation_groups=conversation_groups,
                total_conversations=total_conversations,
                total_messages=total_messages
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching conversations: {str(e)}")

    async def get_conversation_detail(self, conversation_id: str, individual_id: str) -> ConversationDetailSchema:
        """Get detailed conversation with full context"""
        try:
            conversation = self.conversations_collection.find_one({
                "conversation_id": conversation_id,
                "individual_id": individual_id
            })

            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")

            # Transform context messages
            messages = []
            for msg in conversation.get("context", []):
                messages.append(MessageSchema(
                    role=msg.get("role", ""),
                    content=msg.get("content", ""),
                    timestamp=msg.get("timestamp")
                ))

            return ConversationDetailSchema(
                conversation_id=conversation["conversation_id"],
                agent_instance_id=conversation["agent_instance_id"],
                detected_agent=conversation["detected_agent"],
                context=messages,
                created_at=conversation.get("created_at", datetime.now()),
                updated_at=conversation.get("updated_at"),
                is_active=not conversation.get("is_paused", False),
                has_summary=conversation.get("has_summary", False),
                summary=conversation.get("summary")
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching conversation detail: {str(e)}")

    async def get_conversation_analytics(self, individual_id: str, agent_type: Optional[str] = None) -> Dict[str, Any]:
        """Get conversation analytics for the user"""
        try:
            match_filter = {"individual_id": individual_id}
            if agent_type:
                match_filter["detected_agent"] = agent_type

            # Basic stats
            total_conversations = self.conversations_collection.count_documents(match_filter)
            active_conversations = self.conversations_collection.count_documents({
                **match_filter,
                "is_paused": {"$ne": True}
            })

            # Average messages per conversation
            pipeline = [
                {"$match": match_filter},
                {"$group": {
                    "_id": None,
                    "avg_messages": {"$avg": {"$size": "$context"}},
                    "total_messages": {"$sum": {"$size": "$context"}}
                }}
            ]
            
            stats_result = list(self.conversations_collection.aggregate(pipeline))
            avg_messages = stats_result[0]["avg_messages"] if stats_result else 0
            total_messages = stats_result[0]["total_messages"] if stats_result else 0

            # Recent activity (last 7 days)
            week_ago = datetime.now() - timedelta(days=7)
            recent_conversations = self.conversations_collection.count_documents({
                **match_filter,
                "updated_at": {"$gte": week_ago}
            })

            return {
                "total_conversations": total_conversations,
                "active_conversations": active_conversations,
                "average_messages_per_conversation": round(avg_messages, 1),
                "total_messages": total_messages,
                "recent_activity_7d": recent_conversations
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching analytics: {str(e)}")
