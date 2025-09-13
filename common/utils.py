# File: common/utils.py
import json
import uuid
from typing import Dict, Any, List, Optional

def generate_id() -> str:
    """Generate a unique ID"""
    return str(uuid.uuid4())

def format_context_for_model(context: List[Dict[str, str]]) -> str:
    """Format conversation context for use in prompts"""
    context_str = ""
    for turn in context:
        if turn["role"] == "user":
            context_str += f"Patient: {turn['content']}\n"
        else:
            context_str += f"Assistant: {turn['content']}\n"
    return context_str

def parse_key_value_response(response_text: str) -> Dict[str, Any]:
    """Parse a response with key: value format into a dictionary"""
    result = {}
    current_key = None

    for line in response_text.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Check if line starts a new key
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            result[key] = value
            current_key = key
        elif current_key:
            # Append to previous key
            result[current_key] += " " + line

    return result
