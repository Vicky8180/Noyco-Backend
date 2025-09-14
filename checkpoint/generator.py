# checkpoint/generator.py
from typing import List, Dict, Any
import json
import re
import os
from common.gemini_client import get_gemini_client
from common.models import CheckpointType

def get_agent_specific_prompt(
    query: str,
    context_str: str,
    detected_intent: str = None,
    agent_type: str = None,
    limit: int = 2,
    has_context: bool = False
) -> str:
    """
    Generate agent-specific prompts based on detected intent and agent type.
    
    Args:
        query: The user's message
        context_str: Formatted conversation context
        detected_intent: Intent detected by the system
        agent_type: Type of agent assigned
        limit: Number of checkpoints to generate
        has_context: Whether conversation context exists
    
    Returns:
        str: Agent-specific prompt for checkpoint generation
    """
    
    # Define agent-specific prompt templates
    agent_prompts = {
        "emotional": {
            "role": "compassionate emotional support specialist",
            "focus": "grief counseling, bereavement support, terminal illness coping, and emotional healing",
            "questions": [
                "validate feelings and normalize grief responses",
                "explore coping mechanisms and support systems", 
                "assess immediate emotional needs and safety",
                "identify meaningful ways to process emotions"
            ],
            "expected_inputs": ["grief_stage", "support_system", "coping_mechanisms", "emotional_state", "memories", "concerns"]
        },
        
        "accountability": {
            "role": "supportive accountability partner",
            "focus": "habit formation, addiction recovery, behavior change, and maintaining commitments",
            "questions": [
                "set specific, measurable goals and milestones",
                "identify triggers and create prevention strategies",
                "establish check-in schedules and progress tracking",
                "develop reward systems and motivation techniques"
            ],
            "expected_inputs": ["goals", "triggers", "habits", "progress", "challenges", "commitment_level", "accountability_frequency"]
        },
        
        "loneliness": {
            "role": "warm social connection facilitator",
            "focus": "building meaningful relationships, reducing isolation, and fostering social connections",
            "questions": [
                "explore current social connections and relationships",
                "identify interests and activities for meeting people",
                "address social anxiety and confidence building",
                "create actionable plans for social engagement"
            ],
            "expected_inputs": ["social_circle", "interests", "barriers", "confidence_level", "social_goals", "preferred_activities"]
        },
        
        "mental_therapy": {
            "role": "professional therapeutic support specialist",
            "focus": "anxiety management, depression support, trauma processing, and mental health coping strategies",
            "questions": [
                "assess current mental health symptoms and severity",
                "explore therapeutic goals and treatment preferences",
                "identify coping strategies and crisis management plans",
                "discuss professional therapy and medication considerations"
            ],
            "expected_inputs": ["symptoms", "triggers", "coping_strategies", "therapy_history", "medication", "crisis_plan", "goals"]
        },
        
        "social_anxiety": {
            "role": "social skills and confidence coach",
            "focus": "social anxiety management, presentation skills, interview preparation, and confidence building",
            "questions": [
                "understand specific social situations causing anxiety",
                "identify physical and emotional anxiety symptoms",
                "practice relaxation and confidence-building techniques",
                "create step-by-step preparation and practice plans"
            ],
            "expected_inputs": ["anxiety_triggers", "physical_symptoms", "preparation_needs", "practice_opportunities", "confidence_level", "specific_event"]
        }
    }
    
    # Use detected intent or agent type to determine the appropriate prompt
    agent_key = detected_intent or agent_type
    if agent_key and agent_key.lower() in agent_prompts:
        agent_config = agent_prompts[agent_key.lower()]
    else:
        # Default general prompt
        agent_config = {
            "role": "general healthcare assistant",
            "focus": "providing comprehensive healthcare support and guidance",
            "questions": [
                "understand the patient's primary concerns",
                "gather relevant medical and personal history",
                "assess immediate needs and priorities",
                "provide appropriate guidance and next steps"
            ],
            "expected_inputs": ["symptoms", "concerns", "medical_history", "immediate_needs"]
        }
    
    # Build the prompt based on whether we have context
    if has_context:
        prompt = f"""
You are a {agent_config['role']} who specializes in {agent_config['focus']}.

Analyze the following conversation and generate the next {limit} natural follow-up questions that are specifically tailored to your specialty area.

CONVERSATION HISTORY:
{context_str}

YOUR SPECIALIZATION FOCUS:
{agent_config['focus']}

APPROACH GUIDELINES:
{chr(10).join(f"✅ {guideline}" for guideline in agent_config['questions'])}

✅ Keep all questions conversational, empathetic, and professionally appropriate
✅ Make questions follow naturally from the conversation history
✅ Do NOT ask questions that were already answered
✅ Focus on your specialty area: {agent_config['focus']}
✅ Be sensitive to the emotional context and patient's state of mind

Respond with a JSON list of EXACTLY {limit} checkpoints like:
[
  {{
    "text": "question or comment 1",
    "expected_inputs": {json.dumps(agent_config['expected_inputs'][:3])}
  }},
  {{
    "text": "question or comment 2", 
    "expected_inputs": {json.dumps(agent_config['expected_inputs'][3:6] if len(agent_config['expected_inputs']) > 3 else agent_config['expected_inputs'][:2])}
  }}
]
"""
    else:
        # Initial checkpoints generation (no context yet)
        prompt = f"""
You are a {agent_config['role']} who specializes in {agent_config['focus']}.

Analyze the following patient message and generate EXACTLY {limit} initial follow-up questions that are specifically tailored to your specialty area.

Patient message: "{query}"

YOUR SPECIALIZATION FOCUS:
{agent_config['focus']}

APPROACH GUIDELINES:
{chr(10).join(f"✅ {guideline}" for guideline in agent_config['questions'])}

✅ Keep all questions conversational, empathetic, and professionally appropriate
✅ Focus on your specialty area: {agent_config['focus']}
✅ Be sensitive to the emotional context and patient's needs
✅ Ask questions that will help you provide the best specialized support

Respond with a JSON list of EXACTLY {limit} checkpoints like:
[
  {{
    "text": "question or comment 1",
    "expected_inputs": {json.dumps(agent_config['expected_inputs'][:3])}
  }},
  {{
    "text": "question or comment 2",
    "expected_inputs": {json.dumps(agent_config['expected_inputs'][3:6] if len(agent_config['expected_inputs']) > 3 else agent_config['expected_inputs'][:2])}
  }}
]
"""
    
    return prompt

async def generate_checkpoints(
    query: str, 
    task_type: CheckpointType = "Main", 
    context: List[Dict] = None, 
    limit: int = 2,
    detected_intent: str = None,
    agent_type: str = None,
    conversation_context: List[Dict] = None
) -> List[Dict[str, Any]]:
    """
    Generate smart medical assistant-style checkpoints or responses based on patient query.

    Args:
        query: The patient's initial input or concern.
        task_type: Type of checkpoint to generate (Main, SupportAgent, Interrupt)
        context: Optional conversation context for generating follow-up checkpoints
        limit: Maximum number of checkpoints to generate (default: 2)
        detected_intent: The intent detected by the system
        agent_type: The type of agent assigned for this conversation
        conversation_context: Full conversation history for better context

    Returns:
        List[Dict]: List of checkpoint dictionaries with text and expected inputs.
    """
    client = get_gemini_client()
    
    # Use conversation_context if available, otherwise fall back to context
    context_to_use = conversation_context or context
    
    # Format context if available
    context_str = ""
    if context_to_use:
        for turn in context_to_use:
            if turn.get("role") == "user":
                context_str += f"Patient: {turn.get('content', '')}\n"
            else:
                context_str += f"Assistant: {turn.get('content', '')}\n"

    # Get agent-specific prompt based on detected intent and agent type
    prompt = get_agent_specific_prompt(
        query=query,
        context_str=context_str,
        detected_intent=detected_intent,
        agent_type=agent_type,
        limit=limit,
        has_context=bool(context_to_use)
    )

    try:
        # Log the enhanced request details for debugging
        print(f"Generating checkpoints with enhanced context:")
        print(f"  - Detected Intent: {detected_intent}")
        print(f"  - Agent Type: {agent_type}")
        print(f"  - Has Context: {bool(context_to_use)}")
        print(f"  - Query: {query[:100]}...")
        
        response = await client.generate_content(prompt)
        response_text = response.text.strip()

        print(f"Enhanced checkpoint generation completed successfully")

        # First attempt: try direct JSON parsing
        try:
            checkpoints_data = json.loads(response_text)
            return normalize_checkpoints(checkpoints_data)
        except json.JSONDecodeError:
            # If not valid JSON, try extracting JSON from the text (it might be embedded)
            json_match = re.search(r'\[\s*\{.*\}\s*\]', response_text, re.DOTALL)
            if json_match:
                try:
                    checkpoints_data = json.loads(json_match.group(0))
                    return normalize_checkpoints(checkpoints_data)
                except json.JSONDecodeError:
                    pass

            # Fall back to text parsing if JSON extraction fails
            return parse_text_response(response_text)
    except Exception as e:
        print(f"Error generating checkpoints: {e}")
        # Return a single generic checkpoint as fallback
        return [{
            "text": "I'm sorry, but I need to understand your situation better. Could you please tell me more about what you're experiencing or what you need help with?",
            "expected_inputs": ["symptoms", "request_details", "clarification"]
        }]


def normalize_checkpoints(checkpoints_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize and validate the checkpoint data structure."""
    if not checkpoints_data:
        return []

    normalized = []
    for checkpoint in checkpoints_data:
        # Ensure text field exists and is not empty
        if not checkpoint.get("text"):
            continue

        # Normalize expected_inputs field
        if "expected_inputs" not in checkpoint or not isinstance(checkpoint["expected_inputs"], list):
            checkpoint["expected_inputs"] = []

        # Convert spaces to underscores in input names and ensure lowercase
        checkpoint["expected_inputs"] = [
            input_name.lower().replace(' ', '_')
            for input_name in checkpoint["expected_inputs"]
            if input_name
        ]

        normalized.append(checkpoint)

    return normalized


def parse_text_response(response_text: str) -> List[Dict[str, Any]]:
    """Parse non-JSON formatted responses into checkpoint structure."""
    checkpoints = []
    lines = [line.strip() for line in response_text.split('\n') if line.strip()]

    # Pattern to match items, supporting numbered lists, bullets, etc.
    item_pattern = re.compile(r'^(?:\d+[\.\)]\s*|\-\s*|\*\s*|Q\d+:\s*|Question\s*\d+:\s*)')

    current_text = None
    expected_inputs = []

    for i, line in enumerate(lines):
        # Check if this is a new checkpoint
        if item_pattern.match(line) or (i == 0 and not any(item_pattern.match(l) for l in lines)):
            # Save the previous checkpoint if it exists
            if current_text:
                checkpoints.append({
                    "text": current_text,
                    "expected_inputs": expected_inputs
                })
                expected_inputs = []

            # Extract the checkpoint text (remove any leading numbers, bullets, etc.)
            current_text = item_pattern.sub('', line).strip()
        elif current_text:
            # This line belongs to the current checkpoint
            # Check if it's about expected inputs
            if any(keyword in line.lower() for keyword in ["expected input", "possible response", "user might"]):
                # Extract potential input types
                input_text = re.sub(r'^.*?[:\-]', '', line).strip()
                for input_item in re.split(r'[,;]', input_text):
                    clean_input = input_item.strip().lower().replace(' ', '_')
                    if clean_input and len(clean_input) > 1:  # Avoid single character inputs
                        expected_inputs.append(clean_input)
            else:
                # Append to current text if it's a continuation
                current_text += " " + line

    # Add the final checkpoint
    if current_text:
        checkpoints.append({
            "text": current_text,
            "expected_inputs": expected_inputs
        })

    # If we still have no checkpoints, extract any full sentences as checkpoints
    if not checkpoints:
        sentence_pattern = re.compile(r'[^.!?]+[.!?]')
        for sentence in sentence_pattern.findall(response_text):
            if len(sentence.strip()) > 10:  # Only use reasonably long sentences
                checkpoints.append({
                    "text": sentence.strip(),
                    "expected_inputs": []
                })

    return checkpoints
