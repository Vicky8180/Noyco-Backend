# checkpoint/generator.py
from typing import List, Dict, Any
import json
import re
import os
from common.gemini_client import get_gemini_client
from common.models import CheckpointType

async def generate_checkpoints(query: str, task_type: CheckpointType = "Main", context: List[Dict] = None, limit: int = 2) -> List[Dict[str, Any]]:
    """
    Generate smart medical assistant-style checkpoints or responses based on patient query.

    Args:
        query: The patient's initial input or concern.
        task_type: Type of checkpoint to generate (Main, SupportAgent, Interrupt)
        context: Optional conversation context for generating follow-up checkpoints
        limit: Maximum number of checkpoints to generate (default: 2)

    Returns:
        List[Dict]: List of checkpoint dictionaries with text and expected inputs.
    """
    client = get_gemini_client()
    
    # Format context if available
    context_str = ""
    if context:
        for turn in context:
            if turn.get("role") == "user":
                context_str += f"Patient: {turn.get('content', '')}\n"
            else:
                context_str += f"Assistant: {turn.get('content', '')}\n"

    # Adjust the prompt based on whether we have context
    if context:
        prompt = f"""
You are NurseCareBot, a virtual nurse assistant who communicates politely, clearly, and professionally.
You help patients by either:
- asking diagnostic questions for symptom-related issues
- offering relevant, natural responses for non-symptom requests (e.g., health records, prescriptions, reports)

Analyze the following conversation and generate the next {limit} natural follow-up question(s) to continue the conversation naturally.

CONVERSATION HISTORY:
{context_str}

✅ Keep all questions conversational and context-aware.
✅ Make questions follow naturally from the conversation history.
✅ Do NOT ask questions that were already answered.
✅ If it's a medical issue, ask empathetic, helpful questions to understand symptoms.
✅ If it's a request (e.g., 'can I get my BP report'), respond accordingly — offer help, ask clarifying details.

Respond with a JSON list of EXACTLY {limit} checkpoints like:
[
  {{
    "text": "question or comment 1",
    "expected_inputs": ["input1", "input2"]
  }},
  {{
    "text": "question or comment 2",
    "expected_inputs": ["input3"]
  }}
]
"""
    else:
        # Initial checkpoints generation (no context yet)
        prompt = f"""
You are NurseCareBot, a virtual nurse assistant who communicates politely, clearly, and professionally.
You help patients by either:
- asking diagnostic questions for symptom-related issues
- offering relevant, natural responses for non-symptom requests (e.g., health records, prescriptions, reports)

Analyze the following patient message, understand its intent, and generate EXACTLY {limit} initial follow-up questions as if you're starting a nurse patient conversation.

✅ If it's a medical issue, ask empathetic, helpful questions to understand symptoms.
✅ If it's a request (e.g., 'can I get my BP report'), respond accordingly — offer help, ask clarifying details (e.g., 'which date?', 'for whom?'), etc.
✅ Keep all lines conversational and context-aware.
✅ Do NOT ask silly or irrelevant questions.

Patient message: "{query}"

Respond with a JSON list of EXACTLY {limit} checkpoints like:
[
  {{
    "text": "question or comment 1",
    "expected_inputs": ["input1", "input2"]
  }},
  {{
    "text": "question or comment 2",
    "expected_inputs": ["input3"]
  }}
]
"""

    try:
        response = await client.generate_content(prompt)
        response_text = response.text.strip()

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
