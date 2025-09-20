from fastapi import HTTPException, status
from datetime import datetime
from typing import Dict, Any, Optional, List
from .schema import UserProfile, LovedOne, PastStory, EmotionalCompanionAgent, AccountabilityAgent, SocialAnxietyAgent, TherapyAgent, LonelinessAgent, EmotionalGoal, AccountabilityGoal, AnxietyGoal, TherapyGoal, LonelinessGoal
from ..auth.schema import Individual
from ...database.db import get_database
from ...utils.helperFunctions import generate_unique_id
from bson import ObjectId


class UserProfileController:
    """Controller for managing user profiles"""

    def __init__(self):
        self.db = get_database()
        # Initialize database indexes on first use
        self._ensure_database_compatibility()

    def _ensure_database_compatibility(self):
        """Ensure database compatibility by cleaning up conflicting data"""
        try:
            # Clean up any existing documents with null values that conflict with indexes
            self.db.user_profiles.delete_many({"id": None})
            self.db.user_profiles.delete_many({"user_id": None})
        except Exception as e:
            # If there's an error during cleanup, log it but don't fail initialization
            print(f"Database cleanup warning: {e}")

    def _convert_objectid_to_str(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert MongoDB ObjectId to string in a document"""
        if doc is None:
            return doc
        
        if isinstance(doc, dict):
            for key, value in doc.items():
                if isinstance(value, ObjectId):
                    doc[key] = str(value)
                elif isinstance(value, dict):
                    doc[key] = self._convert_objectid_to_str(value)
                elif isinstance(value, list):
                    doc[key] = [self._convert_objectid_to_str(item) if isinstance(item, dict) else str(item) if isinstance(item, ObjectId) else item for item in value]
        
        # Always remove MongoDB _id field
        doc.pop("_id", None)
        return doc

    async def create_user_profile(self, role_entity_id: str, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user profile for a user"""
        
        # Debug: Log the incoming data
        print(f"DEBUG - create_user_profile received data: {profile_data}")
        if "loved_ones" in profile_data:
            print(f"DEBUG - loved_ones data: {profile_data['loved_ones']}")
            for i, loved_one in enumerate(profile_data.get("loved_ones", [])):
                print(f"DEBUG - loved_one {i}: {loved_one}")
                if "memories" in loved_one:
                    print(f"DEBUG - memories for {loved_one.get('name')}: {loved_one['memories']}")
        
        # Check if the role_entity_id exists in the individuals collection
        individual = self.db.individuals.find_one({"id": role_entity_id})
        if not individual:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Individual user with ID {role_entity_id} not found"
            )

        # Check if a profile with the same profile_name already exists for this user
        profile_name = profile_data.get("profile_name")
        existing_profile = self.db.user_profiles.find_one({
            "role_entity_id": role_entity_id,
            "profile_name": profile_name
        })
        
        if existing_profile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User profile with name '{profile_name}' already exists for user {role_entity_id}"
            )

        # Generate unique user_profile_id
        user_profile_id = generate_unique_id("user_profile")
        
        # Validate required fields
        if not profile_data.get("phone"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number is required"
            )
        
        # Create UserProfile instance with validation
        user_profile = UserProfile(
            user_profile_id=user_profile_id,
            role_entity_id=role_entity_id,
            profile_name=profile_data.get("profile_name"),
            name=profile_data.get("name", individual["name"]),  # Use individual's name as default
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            phone=profile_data.get("phone"),
            location=profile_data.get("location"),
            language=profile_data.get("language"),
            hobbies=profile_data.get("hobbies", []),
            hates=profile_data.get("hates", []),
            interests=profile_data.get("interests", []),
            loved_ones=[LovedOne(**loved_one) for loved_one in profile_data.get("loved_ones", [])],
            past_stories=[PastStory(**story) for story in profile_data.get("past_stories", [])],
            preferences=profile_data.get("preferences", {}),
            personality_traits=profile_data.get("personality_traits", []),
            health_info=profile_data.get("health_info", {}),
            emotional_baseline=profile_data.get("emotional_baseline"),
            is_active=profile_data.get("is_active", True)
        )

        # Convert to dict for database insertion
        profile_dict = user_profile.model_dump()
        
        # Handle potential index conflicts by setting id and user_id to user_profile_id
        # This maintains compatibility with existing database indexes
        profile_dict["id"] = user_profile_id
        profile_dict["user_id"] = user_profile_id  # Set to unique profile ID to avoid conflicts
        
        try:
            # Insert into database
            result = self.db.user_profiles.insert_one(profile_dict)
        except Exception as e:
            # If there's still a conflict, it might be due to existing null values
            if "duplicate key error" in str(e):
                if "id: null" in str(e):
                    # Clean up any existing documents with null id
                    self.db.user_profiles.delete_many({"id": None})
                elif "user_id: null" in str(e):
                    # Clean up any existing documents with null user_id
                    self.db.user_profiles.delete_many({"user_id": None})
                # Try the insert again
                result = self.db.user_profiles.insert_one(profile_dict)
            else:
                raise e

        # Convert ObjectIds and remove _id
        profile_dict = self._convert_objectid_to_str(profile_dict)

        return {
            "user_profile_id": user_profile_id,
            "role_entity_id": role_entity_id,
            "message": "User profile created successfully",
            "profile": profile_dict
        }

    async def get_all_user_profiles(self, role_entity_id: str) -> List[Dict[str, Any]]:
        """Get all user profiles for a specific user"""
        
        # Check if the role_entity_id exists in the individuals collection
        individual = self.db.individuals.find_one({"id": role_entity_id})
        if not individual:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Individual user with ID {role_entity_id} not found"
            )

        # Get all user profiles for this role_entity_id
        profiles_cursor = self.db.user_profiles.find({"role_entity_id": role_entity_id})
        profiles = list(profiles_cursor)

        # Convert ObjectIds and remove _id for each profile
        profiles = [self._convert_objectid_to_str(profile) for profile in profiles]
        
        return profiles

    async def get_user_profile(self, role_entity_id: str, user_profile_id: str) -> Dict[str, Any]:
        """Get a specific user profile by role_entity_id and user_profile_id"""
        
        # Check if the role_entity_id exists in the individuals collection
        individual = self.db.individuals.find_one({"id": role_entity_id})
        if not individual:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Individual user with ID {role_entity_id} not found"
            )

        # Get specific user profile
        profile = self.db.user_profiles.find_one({
            "role_entity_id": role_entity_id,
            "user_profile_id": user_profile_id
        })
        
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User profile with ID {user_profile_id} not found for user {role_entity_id}"
            )

        # Convert ObjectIds and remove _id
        profile = self._convert_objectid_to_str(profile)
        return profile

    async def update_user_profile(self, role_entity_id: str, user_profile_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a specific user profile"""
        
        # Debug: Log the incoming update data
        print(f"DEBUG - update_user_profile received data: {update_data}")
        if "loved_ones" in update_data:
            print(f"DEBUG - loved_ones update data: {update_data['loved_ones']}")
            for i, loved_one in enumerate(update_data.get("loved_ones", [])):
                print(f"DEBUG - loved_one {i}: {loved_one}")
                if "memories" in loved_one:
                    print(f"DEBUG - memories for {loved_one.get('name')}: {loved_one['memories']}")
        
        # Check if the role_entity_id exists in the individuals collection
        individual = self.db.individuals.find_one({"id": role_entity_id})
        if not individual:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Individual user with ID {role_entity_id} not found"
            )

        # Check if user profile exists
        existing_profile = self.db.user_profiles.find_one({
            "role_entity_id": role_entity_id,
            "user_profile_id": user_profile_id
        })
        
        if not existing_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User profile with ID {user_profile_id} not found for user {role_entity_id}"
            )

        # If updating profile_name, check for conflicts
        if "profile_name" in update_data:
            new_profile_name = update_data["profile_name"]
            existing_name_profile = self.db.user_profiles.find_one({
                "role_entity_id": role_entity_id,
                "profile_name": new_profile_name,
                "user_profile_id": {"$ne": user_profile_id}  # Exclude current profile
            })
            
            if existing_name_profile:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User profile with name '{new_profile_name}' already exists for user {role_entity_id}"
                )

        # Process loved_ones and past_stories through schemas to ensure proper validation
        if "loved_ones" in update_data:
            update_data["loved_ones"] = [LovedOne(**loved_one).model_dump() for loved_one in update_data["loved_ones"]]
        
        if "past_stories" in update_data:
            update_data["past_stories"] = [PastStory(**story).model_dump() for story in update_data["past_stories"]]

        # Update timestamp
        update_data["updated_at"] = datetime.utcnow()

        # Update the profile
        result = self.db.user_profiles.update_one(
            {
                "role_entity_id": role_entity_id,
                "user_profile_id": user_profile_id
            },
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No changes were made to the user profile"
            )

        # Return updated profile
        updated_profile = self.db.user_profiles.find_one({
            "role_entity_id": role_entity_id,
            "user_profile_id": user_profile_id
        })
        updated_profile = self._convert_objectid_to_str(updated_profile)
        
        return {
            "message": "User profile updated successfully",
            "profile": updated_profile
        }

    async def delete_user_profile(self, role_entity_id: str, user_profile_id: str) -> Dict[str, Any]:
        """Delete a specific user profile"""
        
        # Check if the role_entity_id exists in the individuals collection
        individual = self.db.individuals.find_one({"id": role_entity_id})
        if not individual:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Individual user with ID {role_entity_id} not found"
            )

        # Check if user profile exists
        existing_profile = self.db.user_profiles.find_one({
            "role_entity_id": role_entity_id,
            "user_profile_id": user_profile_id
        })
        
        if not existing_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User profile with ID {user_profile_id} not found for user {role_entity_id}"
            )

        # Delete the profile
        result = self.db.user_profiles.delete_one({
            "role_entity_id": role_entity_id,
            "user_profile_id": user_profile_id
        })

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete user profile"
            )

        return {
            "message": "User profile deleted successfully",
            "user_profile_id": user_profile_id,
            "role_entity_id": role_entity_id
        }

    # ---------- Goal Update Methods ----------
    
    async def update_emotional_goal(self, user_profile_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update or create emotional companion agent goal"""
        
        # First, validate that the user_profile_id exists in user_profiles collection
        user_profile = self.db.user_profiles.find_one({"user_profile_id": user_profile_id})
        if not user_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User profile with ID {user_profile_id} not found"
            )
        
        collection_name = "emotional_companion_agents"
        
        # Create goal data
        goal_data = {
            "title": update_data.get("title", "Emotional Wellness Goal"),
            "description": update_data.get("description"),
            "due_date": update_data.get("due_date"),
            "status": update_data.get("status", "active"),
            "check_ins": [],
            "streak": 0,
            "max_streak": 0,
            "progress_tracking": [],
            "mood_trend": []
        }
        
        # Create EmotionalGoal instance to get goal_id
        emotional_goal = EmotionalGoal(**goal_data)
        
        # Check if agent document exists
        existing_agent = self.db[collection_name].find_one({"user_profile_id": user_profile_id})
        
        if existing_agent:
            # Append new goal to existing emotional_goals array
            result = self.db[collection_name].update_one(
                {"user_profile_id": user_profile_id},
                {
                    "$push": {"emotional_goals": emotional_goal.model_dump()},
                    "$set": {
                        "memory_stack": update_data.get("memory_stack", existing_agent.get("memory_stack", [])),
                        "comfort_tips": update_data.get("comfort_tips", existing_agent.get("comfort_tips", [])),
                        "last_interaction": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            agent_id = existing_agent.get("id")
        else:
            # Create new agent document with goals as array
            agent_data = {
                "user_profile_id": user_profile_id,
                "memory_stack": update_data.get("memory_stack", []),
                "comfort_tips": update_data.get("comfort_tips", []),
                "emotional_goals": [emotional_goal.model_dump()],  # Array with first goal
                "last_interaction": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            agent = EmotionalCompanionAgent(**agent_data)
            agent_dict = agent.model_dump()
            
            result = self.db[collection_name].insert_one(agent_dict)
            agent_id = agent.id
        
        return {
            "message": "Emotional goal added successfully",
            "goal_id": emotional_goal.goal_id,
            "user_profile_id": user_profile_id,
            "agent_id": agent_id
        }
    
    async def update_accountability_goal(self, user_profile_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update or create accountability agent goal"""
        
        # First, validate that the user_profile_id exists in user_profiles collection
        user_profile = self.db.user_profiles.find_one({"user_profile_id": user_profile_id})
        if not user_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User profile with ID {user_profile_id} not found"
            )
        
        collection_name = "accountability_agents"
        
        # Create goal data
        goal_data = {
            "title": update_data.get("title", "Accountability Goal"),
            "description": update_data.get("description"),
            "due_date": update_data.get("due_date"),
            "status": update_data.get("status", "active"),
            "check_ins": [],
            "streak": 0,
            "max_streak": 0,
            "progress_tracking": [],
            "mood_trend": []
        }
        
        accountability_goal = AccountabilityGoal(**goal_data)
        
        # Check if agent document exists
        existing_agent = self.db[collection_name].find_one({"user_profile_id": user_profile_id})
        
        if existing_agent:
            # Append new goal to existing accountability_goals array
            result = self.db[collection_name].update_one(
                {"user_profile_id": user_profile_id},
                {
                    "$push": {"accountability_goals": accountability_goal.model_dump()},
                    "$set": {
                        "last_interaction": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            agent_id = existing_agent.get("id")
        else:
            # Create new agent document with goals as array
            agent_data = {
                "user_profile_id": user_profile_id,
                "accountability_goals": [accountability_goal.model_dump()],  # Array with first goal
                "last_interaction": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            agent = AccountabilityAgent(**agent_data)
            agent_dict = agent.model_dump()
            
            result = self.db[collection_name].insert_one(agent_dict)
            agent_id = agent.id
        
        return {
            "message": "Accountability goal added successfully",
            "goal_id": accountability_goal.goal_id,
            "user_profile_id": user_profile_id,
            "agent_id": agent_id
        }
    
    async def update_anxiety_goal(self, user_profile_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update or create social anxiety agent goal"""
        
        # First, validate that the user_profile_id exists in user_profiles collection
        user_profile = self.db.user_profiles.find_one({"user_profile_id": user_profile_id})
        if not user_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User profile with ID {user_profile_id} not found"
            )
        
        collection_name = "anxiety_agents"
        
        goal_data = {
            "title": update_data.get("title", "Anxiety Management Goal"),
            "description": update_data.get("description"),
            "due_date": update_data.get("due_date"),
            "status": update_data.get("status", "active"),
            "event_date": update_data.get("event_date"),
            "event_type": update_data.get("event_type"),
            "anxiety_level": update_data.get("anxiety_level"),
            "nervous_thoughts": update_data.get("nervous_thoughts", []),
            "physical_symptoms": update_data.get("physical_symptoms", []),
            "check_ins": [],
            "streak": 0,
            "max_streak": 0,
            "progress_tracking": [],
            "mood_trend": []
        }
        
        anxiety_goal = AnxietyGoal(**goal_data)
        
        # Check if agent document exists
        existing_agent = self.db[collection_name].find_one({"user_profile_id": user_profile_id})
        
        if existing_agent:
            # Append new goal to existing anxiety_goals array
            result = self.db[collection_name].update_one(
                {"user_profile_id": user_profile_id},
                {
                    "$push": {"anxiety_goals": anxiety_goal.model_dump()},
                    "$set": {
                        "last_interaction": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            agent_id = existing_agent.get("id")
        else:
            # Create new agent document with goals as array
            agent_data = {
                "user_profile_id": user_profile_id,
                "anxiety_goals": [anxiety_goal.model_dump()],  # Array with first goal
                "last_interaction": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            agent = SocialAnxietyAgent(**agent_data)
            agent_dict = agent.model_dump()
            
            result = self.db[collection_name].insert_one(agent_dict)
            agent_id = agent.id
        
        return {
            "message": "Anxiety goal added successfully",
            "goal_id": anxiety_goal.goal_id,
            "user_profile_id": user_profile_id,
            "agent_id": agent_id
        }
    
    async def update_therapy_goal(self, user_profile_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update or create therapy agent goal"""
        
        # First, validate that the user_profile_id exists in user_profiles collection
        user_profile = self.db.user_profiles.find_one({"user_profile_id": user_profile_id})
        if not user_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User profile with ID {user_profile_id} not found"
            )
        
        collection_name = "therapy_agents"
        
        goal_data = {
            "title": update_data.get("title", "Therapy Goal"),
            "description": update_data.get("description"),
            "due_date": update_data.get("due_date"),
            "status": update_data.get("status", "active"),
            "check_ins": [],
            "streak": 0,
            "max_streak": 0,
            "progress_tracking": [],
            "mood_trend": []
        }
        
        therapy_goal = TherapyGoal(**goal_data)
        
        # Check if agent document exists
        existing_agent = self.db[collection_name].find_one({"user_profile_id": user_profile_id})
        
        if existing_agent:
            # Append new goal to existing therapy_goals array
            result = self.db[collection_name].update_one(
                {"user_profile_id": user_profile_id},
                {
                    "$push": {"therapy_goals": therapy_goal.model_dump()},
                    "$set": {
                        "last_interaction": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            agent_id = existing_agent.get("id")
        else:
            # Create new agent document with goals as array
            agent_data = {
                "user_profile_id": user_profile_id,
                "therapy_goals": [therapy_goal.model_dump()],  # Array with first goal
                "last_interaction": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            agent = TherapyAgent(**agent_data)
            agent_dict = agent.model_dump()
            
            result = self.db[collection_name].insert_one(agent_dict)
            agent_id = agent.id
        
        return {
            "message": "Therapy goal added successfully",
            "goal_id": therapy_goal.goal_id,
            "user_profile_id": user_profile_id,
            "agent_id": agent_id
        }
    
    async def update_loneliness_goal(self, user_profile_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update or create loneliness agent goal"""
        
        # First, validate that the user_profile_id exists in user_profiles collection
        user_profile = self.db.user_profiles.find_one({"user_profile_id": user_profile_id})
        if not user_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User profile with ID {user_profile_id} not found"
            )
        
        collection_name = "loneliness_agents"
        
        goal_data = {
            "title": update_data.get("title", "Loneliness Support Goal"),
            "description": update_data.get("description"),
            "due_date": update_data.get("due_date"),
            "status": update_data.get("status", "active"),
            "check_ins": [],
            "streak": 0,
            "max_streak": 0,
            "progress_tracking": [],
            "mood_trend": []
        }
        
        loneliness_goal = LonelinessGoal(**goal_data)
        
        # Check if agent document exists
        existing_agent = self.db[collection_name].find_one({"user_profile_id": user_profile_id})
        
        if existing_agent:
            # Append new goal to existing loneliness_goals array
            result = self.db[collection_name].update_one(
                {"user_profile_id": user_profile_id},
                {
                    "$push": {"loneliness_goals": loneliness_goal.model_dump()},
                    "$set": {
                        "last_interaction": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            agent_id = existing_agent.get("id")
        else:
            # Create new agent document with goals as array
            agent_data = {
                "user_profile_id": user_profile_id,
                "loneliness_goals": [loneliness_goal.model_dump()],  # Array with first goal
                "last_interaction": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            agent = LonelinessAgent(**agent_data)
            agent_dict = agent.model_dump()
            
            result = self.db[collection_name].insert_one(agent_dict)
            agent_id = agent.id
        
        return {
            "message": "Loneliness goal added successfully",
            "goal_id": loneliness_goal.goal_id,
            "user_profile_id": user_profile_id,
            "agent_id": agent_id
        }

    # ---------- Goal Fetch Methods ----------
    
    async def get_emotional_goals(self, role_entity_id: str) -> List[Dict[str, Any]]:
        """Get all emotional companion goals for a user"""
        
        # Get user profile to access user_profile_id
        profiles = await self.get_all_user_profiles(role_entity_id)
        if not profiles:
            return []
        
        # For now, use the first profile - you might want to handle multiple profiles differently
        user_profile_id = profiles[0]["user_profile_id"]
        
        # Get emotional agent data
        emotional_agent = self.db.emotional_companion_agents.find_one({"user_profile_id": user_profile_id})
        if not emotional_agent:
            return []
        
        goals = emotional_agent.get("emotional_goals", [])
        
        # Convert and clean goals
        for goal in goals:
            goal = self._convert_objectid_to_str(goal)
            goal["agentType"] = "emotional_companion"
            goal["created_at"] = goal.get("created_at", datetime.utcnow()).isoformat() if isinstance(goal.get("created_at"), datetime) else goal.get("created_at")
        
        return goals
    
    async def get_accountability_goals(self, role_entity_id: str) -> List[Dict[str, Any]]:
        """Get all accountability goals for a user"""
        
        # Get user profile to access user_profile_id
        profiles = await self.get_all_user_profiles(role_entity_id)
        if not profiles:
            return []
        
        user_profile_id = profiles[0]["user_profile_id"]
        
        # Get accountability agent data
        accountability_agent = self.db.accountability_agents.find_one({"user_profile_id": user_profile_id})
        if not accountability_agent:
            return []
        
        goals = accountability_agent.get("accountability_goals", [])
        
        # Convert and clean goals
        for goal in goals:
            goal = self._convert_objectid_to_str(goal)
            goal["agentType"] = "accountability_buddy"
            goal["created_at"] = goal.get("created_at", datetime.utcnow()).isoformat() if isinstance(goal.get("created_at"), datetime) else goal.get("created_at")
        
        return goals
    
    async def get_anxiety_goals(self, role_entity_id: str) -> List[Dict[str, Any]]:
        """Get all social anxiety goals for a user"""
        
        # Get user profile to access user_profile_id
        profiles = await self.get_all_user_profiles(role_entity_id)
        if not profiles:
            return []
        
        user_profile_id = profiles[0]["user_profile_id"]
        
        # Get anxiety agent data
        anxiety_agent = self.db.anxiety_agents.find_one({"user_profile_id": user_profile_id})
        if not anxiety_agent:
            return []
        
        goals = anxiety_agent.get("anxiety_goals", [])
        
        # Convert and clean goals
        for goal in goals:
            goal = self._convert_objectid_to_str(goal)
            goal["agentType"] = "social_prep"
            goal["created_at"] = goal.get("created_at", datetime.utcnow()).isoformat() if isinstance(goal.get("created_at"), datetime) else goal.get("created_at")
        
        return goals
    
    async def get_therapy_goals(self, role_entity_id: str) -> List[Dict[str, Any]]:
        """Get all therapy goals for a user"""
        
        # Get user profile to access user_profile_id
        profiles = await self.get_all_user_profiles(role_entity_id)
        if not profiles:
            return []
        
        user_profile_id = profiles[0]["user_profile_id"]
        
        # Get therapy agent data
        therapy_agent = self.db.therapy_agents.find_one({"user_profile_id": user_profile_id})
        if not therapy_agent:
            return []
        
        goals = therapy_agent.get("therapy_goals", [])
        
        # Convert and clean goals
        for goal in goals:
            goal = self._convert_objectid_to_str(goal)
            goal["agentType"] = "therapy_checkin"
            goal["created_at"] = goal.get("created_at", datetime.utcnow()).isoformat() if isinstance(goal.get("created_at"), datetime) else goal.get("created_at")
        
        return goals
    
    async def get_loneliness_goals(self, role_entity_id: str) -> List[Dict[str, Any]]:
        """Get all loneliness goals for a user"""
        
        # Get user profile to access user_profile_id
        profiles = await self.get_all_user_profiles(role_entity_id)
        if not profiles:
            return []
        
        user_profile_id = profiles[0]["user_profile_id"]
        
        # Get loneliness agent data
        loneliness_agent = self.db.loneliness_agents.find_one({"user_profile_id": user_profile_id})
        if not loneliness_agent:
            return []
        
        goals = loneliness_agent.get("loneliness_goals", [])
        
        # Convert and clean goals
        for goal in goals:
            goal = self._convert_objectid_to_str(goal)
            goal["agentType"] = "loneliness_support"
            goal["created_at"] = goal.get("created_at", datetime.utcnow()).isoformat() if isinstance(goal.get("created_at"), datetime) else goal.get("created_at")
        
        return goals
