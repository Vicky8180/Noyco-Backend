
# =======================
# routes.py (PARALLEL EXECUTION OPTIMIZATION)
# =======================

from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from dotenv import load_dotenv
from typing import Dict, List
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time

from .schema import ChatRequest, ChatResponse, ConversationMessage, AgentType
from .intent_detector import IntentDetector
from .agent_selector import AgentSelector  
from .entry_chatbot import EntryChatbot

# Load environment variables
load_dotenv()

app = APIRouter(prefix="/initial", tags=["Initial Call Handler"])

# Initialize components
GEMINI_API_KEY = "AIzaSyBHlMf_Ri8w8QT1ClQwS1ZBkgzLskbh4ZQ"
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is required")

intent_detector = IntentDetector(GEMINI_API_KEY)
agent_selector = AgentSelector()
entry_chatbot = EntryChatbot(GEMINI_API_KEY)

# Thread pool for parallel execution
executor = ThreadPoolExecutor(max_workers=6)

# Storage
conversations: Dict[str, List[ConversationMessage]] = {}
user_agents: Dict[str, Dict] = {}

def clear_user_intent_state_internal(user_id: str) -> bool:
    """
    Internal function to clear user intent state - bypasses authentication
    This is called directly from livekit.py for session resets
    """
    cleared_any = False
    
    if user_id in conversations:
        del conversations[user_id]
        cleared_any = True
        print(f"Cleared conversation history for user {user_id}")
    
    if user_id in user_agents:
        del user_agents[user_id]
        cleared_any = True
        print(f"Cleared agent assignment for user {user_id}")
    
    # Also clear common fallback user IDs to be thorough
    fallback_ids = ["default_user", "profile_default"]
    for fallback_id in fallback_ids:
        if fallback_id in conversations:
            del conversations[fallback_id]
            cleared_any = True
            print(f"Cleared fallback conversation history for {fallback_id}")
        
        if fallback_id in user_agents:
            del user_agents[fallback_id]
            cleared_any = True
            print(f"Cleared fallback agent assignment for {fallback_id}")
    
    return cleared_any

async def run_intent_detection_parallel(conversation_history: List[ConversationMessage]) -> "IntentResult":
    """Run intent detection in parallel using thread pool"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        executor, 
        intent_detector.detect_intent_with_gemini,
        conversation_history
    )

async def run_chatbot_response_parallel(message: str, conversation_history: List[ConversationMessage], needs_more_info: bool) -> str:
    """Run chatbot response generation in parallel using thread pool"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        executor,
        entry_chatbot.generate_response,
        message,
        conversation_history,
        needs_more_info
    )

def assign_agent(user_id: str, agent_selection, intent_result, conversation_turn: int):
    """Assign an agent to a user when confidence threshold is reached"""
    if agent_selection.should_route:
        user_agents[user_id] = {
            'selected_agent': agent_selection.selected_agent,
            'agent_name': agent_selection.agent_name,
            'detected_intent': intent_result.intent,
            'confidence': intent_result.confidence,
            'should_route': True,
            'assigned_at_turn': conversation_turn,
            'timestamp': time.time()
        }
        print(f"Agent assigned to user {user_id}: {agent_selection.agent_name} (confidence: {intent_result.confidence:.1%})")

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Optimized chat endpoint with parallel execution of intent detection and chatbot response"""
    
    try:
        start_time = time.time()
        user_id = request.user_id or "default_user"
        
        # Initialize conversation history
        if user_id not in conversations:
            conversations[user_id] = []
        
        conversation_history = request.conversation_history + conversations[user_id]
        user_message = ConversationMessage(role="user", content=request.message)
        conversation_history.append(user_message)
        
        conversation_turn = len([msg for msg in conversation_history if msg.role == "user"])
        
        # Check if user already has an assigned agent
        if user_id in user_agents:
            assigned_agent = user_agents[user_id]
            print(f"Using assigned agent for user {user_id}: {assigned_agent['agent_name']}")
            
            # Generate response immediately - no need for intent detection
            bot_response = await run_chatbot_response_parallel(
                request.message, 
                conversation_history[:-1], 
                needs_more_info=False
            )
            
            response_data = ChatResponse(
                response=bot_response,
                detected_intent=assigned_agent['detected_intent'],
                confidence=assigned_agent['confidence'],
                selected_agent=assigned_agent['selected_agent'],
                selected_agent_name=assigned_agent['agent_name'],
                should_route=True,
                conversation_turn=conversation_turn,
                needs_more_conversation=False
            )
            
        else:
            # No agent assigned - run both intent detection and chatbot response in parallel
            print(f"Running parallel tasks for user {user_id}, turn {conversation_turn}")
            
            # Start both tasks in parallel
            parallel_start = time.time()
            
            # Create tasks for parallel execution
            intent_task = asyncio.create_task(
                run_intent_detection_parallel(conversation_history)
            )
            
            # Start with assumption we need more info, will adjust based on intent result
            chatbot_task = asyncio.create_task(
                run_chatbot_response_parallel(
                    request.message, 
                    conversation_history[:-1], 
                    needs_more_info=True
                )
            )
            
            # Wait for both tasks to complete
            try:
                # Use asyncio.gather for proper parallel execution with timeout
                intent_result, bot_response = await asyncio.wait_for(
                    asyncio.gather(intent_task, chatbot_task),
                    timeout=8.0  # 8 second timeout for both tasks
                )
                
                parallel_time = time.time() - parallel_start
                print(f"Parallel execution completed in {parallel_time:.2f}s")
                print(f"Intent: {intent_result.intent} ({intent_result.confidence:.1%})")
                
            except asyncio.TimeoutError:
                print("Parallel execution timeout - using fallbacks")
                
                # Try to get completed results, use fallbacks for incomplete ones
                intent_result = None
                bot_response = None
                
                if intent_task.done():
                    intent_result = intent_task.result()
                else:
                    intent_task.cancel()
                    intent_result = intent_detector.create_timeout_fallback()
                
                if chatbot_task.done():
                    bot_response = chatbot_task.result()
                else:
                    chatbot_task.cancel()
                    bot_response = "I'm here to listen and support you. What's on your mind today?"
            
            # Process agent selection
            agent_selection = agent_selector.select_agent(intent_result, conversation_turn)
            
            print(f"Agent selection: should_route={agent_selection.should_route}, agent={agent_selection.agent_name}")
            
            # Check if this should trigger agent assignment
            if agent_selection.should_route:
                assign_agent(user_id, agent_selection, intent_result, conversation_turn)
            
            # Prepare response data
            response_data = ChatResponse(
                response=bot_response,
                detected_intent=intent_result.intent if agent_selection.should_route else None,
                confidence=intent_result.confidence if agent_selection.should_route else None,
                selected_agent=agent_selection.selected_agent if agent_selection.should_route else None,
                selected_agent_name=agent_selection.agent_name if agent_selection.should_route else None,
                should_route=agent_selection.should_route,
                conversation_turn=conversation_turn,
                needs_more_conversation=agent_selection.needs_more_conversation
            )
        
        # Store conversation
        bot_message = ConversationMessage(role="assistant", content=response_data.response)
        conversation_history.append(bot_message)
        conversations[user_id] = conversation_history[-20:]  # Keep last 20 messages
        
        total_time = time.time() - start_time
        print(f"Total request time: {total_time:.2f}s")
        
        return response_data
        
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

async def warm_up_models():
    """Warm up models on startup with parallel execution"""
    try:
        # Warm up both models in parallel
        warmup_tasks = [
            run_intent_detection_parallel([ConversationMessage(role="user", content="Hello")]),
            run_chatbot_response_parallel("Hello", [], True)
        ]
        
        await asyncio.gather(*warmup_tasks)
        # Suppress model warmup success message to reduce startup noise
        # logging.info("Models warmed up successfully")
        
    except Exception as e:
        logging.error(f"Model warmup failed: {e}")

@app.on_event("startup")
async def startup_event():
    """Warm up models on startup"""
    asyncio.create_task(warm_up_models())

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Agent Routing System is running", "status": "healthy"}

@app.get("/agents")
async def get_agents():
    """Get list of available agents with their proper names"""
    agents = {
        "emotional_companion": {
            "name": "Emotional Companion Agent",
            "description": "Support elderly or terminally ill users emotionally. Listens, comforts, stores memories."
        },
        "accountability_buddy": {
            "name": "Accountability Buddy", 
            "description": "Help users stick to life changes like moving cities, going sober, or starting therapy."
        },
        "voice_companion": {
            "name": "Chronically Lonely People Agent",
            "description": "Provide companionship and track emotional state passively over time."
        },
        "therapy_checkin": {
            "name": "Mental Health Check-In",
            "description": "Short emotional support calls with mood tracking and relaxation tools."
        },
        "social_anxiety_prep": {
            "name": "Pre-Social Anxiety Prep Agent",
            "description": "Prepare user before stressful social events (calls, dates, meetings)."
        }
    }
    return agents

@app.delete("/conversation/{user_id}")
async def clear_conversation(user_id: str):
    """Clear conversation history and agent assignment for a user"""
    cleared_items = []
    
    if user_id in conversations:
        del conversations[user_id]
        cleared_items.append("conversation history")
    
    if user_id in user_agents:
        del user_agents[user_id]
        cleared_items.append("agent assignment")
    
    if cleared_items:
        return {"message": f"Cleared {', '.join(cleared_items)} for user {user_id}"}
    return {"message": "No data found for this user"}

@app.delete("/agent/{user_id}")
async def reset_agent_assignment(user_id: str):
    """Reset agent assignment for a user without clearing conversation history"""
    if user_id in user_agents:
        agent_name = user_agents[user_id].get('agent_name', 'Unknown')
        del user_agents[user_id]
        return {"message": f"Reset agent assignment ({agent_name}) for user {user_id}. Intent will be re-detected."}
    return {"message": "No agent assignment found for this user"}

@app.get("/debug/state")
async def get_system_state():
    """Debug endpoint to see current system state"""
    return {
        "active_conversations": len(conversations),
        "assigned_agents": len(user_agents),
        "users_with_conversations": list(conversations.keys()),
        "users_with_agents": {
            user_id: {
                "agent_name": data['agent_name'],
                "confidence": data['confidence'],
                "assigned_at_turn": data['assigned_at_turn'],
                "detected_intent": data['detected_intent']
            }
            for user_id, data in user_agents.items()
        }
    }

@app.get("/conversation/{user_id}/analysis")
async def get_conversation_analysis(user_id: str):
    """Get detailed analysis of the current conversation state"""
    if user_id not in conversations or not conversations[user_id]:
        return {"message": "No conversation found for this user"}
    
    conversation_history = conversations[user_id]
    conversation_turn = len([msg for msg in conversation_history if msg.role == "user"])
    
    # Check for assigned agent
    if user_id in user_agents:
        assigned_agent = user_agents[user_id]
        return {
            "user_id": user_id,
            "conversation_turns": conversation_turn,
            "agent_status": "assigned",
            "detected_intent": assigned_agent['detected_intent'],
            "confidence": assigned_agent['confidence'],
            "selected_agent": assigned_agent['selected_agent'].value,
            "agent_name": assigned_agent['agent_name'],
            "should_route": True,
            "needs_more_conversation": False,
            "assigned_at_turn": assigned_agent['assigned_at_turn'],
            "conversation_messages": len(conversation_history),
            "agent_reasoning": f"Agent assigned at turn {assigned_agent['assigned_at_turn']} with {assigned_agent['confidence']:.1%} confidence"
        }
    
    # No agent assigned yet - run fresh analysis
    try:
        intent_result = await run_intent_detection_parallel(conversation_history)
        agent_selection = agent_selector.select_agent(intent_result, conversation_turn)
        
        return {
            "user_id": user_id,
            "conversation_turns": conversation_turn,
            "agent_status": "analyzing",
            "detected_intent": intent_result.intent,
            "confidence": intent_result.confidence,
            "keywords": intent_result.keywords,
            "reasoning": intent_result.reasoning,
            "selected_agent": agent_selection.selected_agent.value,
            "agent_name": agent_selection.agent_name,
            "should_route": agent_selection.should_route,
            "needs_more_conversation": agent_selection.needs_more_conversation,
            "agent_reasoning": agent_selection.reasoning,
            "conversation_messages": len(conversation_history)
        }
    except Exception as e:
        return {
            "user_id": user_id,
            "conversation_turns": conversation_turn,
            "agent_status": "error",
            "error": str(e),
            "conversation_messages": len(conversation_history)
        }
