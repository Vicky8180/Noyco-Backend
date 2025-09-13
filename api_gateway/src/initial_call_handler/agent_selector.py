

# =======================
# agent_selector.py (UPDATED)
# =======================

from .schema import AgentType, AgentSelection, IntentResult

class AgentSelector:
    def __init__(self):
        self.intent_to_agent = {
            "emotional_support": AgentType.EMOTIONAL_COMPANION,
            "accountability": AgentType.ACCOUNTABILITY_BUDDY,
            "companionship": AgentType.VOICE_COMPANION,
            "mental_health": AgentType.THERAPY_CHECKIN,
            "social_preparation": AgentType.SOCIAL_ANXIETY_PREP
        }
        
        # Updated threshold - route at 80%+ confidence as requested
        self.routing_confidence_threshold = 0.80
        self.min_turns_before_routing = 1  # Allow routing from turn 1 with sufficient confidence

    def select_agent(self, intent_result: IntentResult, conversation_turn: int) -> AgentSelection:
        """Select agent with 80%+ confidence and responsive routing"""
        
        # Normalize intent to lowercase to handle case sensitivity
        normalized_intent = intent_result.intent.lower() if intent_result.intent else "none"
        
        # Check for routing eligibility first (80%+ confidence with valid intent)
        if (normalized_intent != "none" and 
            normalized_intent in self.intent_to_agent and 
            intent_result.confidence >= self.routing_confidence_threshold):
            
            selected_agent = self.intent_to_agent[normalized_intent]
            
            # Allow routing from turn 1 if confidence is 80%+
            return AgentSelection(
                selected_agent=selected_agent,
                agent_name=selected_agent.get_agent_name(),
                confidence=intent_result.confidence,
                reasoning=f"High confidence ({intent_result.confidence:.1%}) routing to {selected_agent.get_agent_name()} on turn {conversation_turn}",
                should_route=True,
                needs_more_conversation=False
            )
        
        # For very early conversation (turn 1) with lower confidence, still gather info
        if conversation_turn < self.min_turns_before_routing and intent_result.confidence < self.routing_confidence_threshold:
            return AgentSelection(
                selected_agent=AgentType.VOICE_COMPANION,
                agent_name="General Conversation",
                confidence=0.0,
                reasoning=f"Gathering information (turn {conversation_turn}) - confidence {intent_result.confidence:.1%} below threshold",
                should_route=False,
                needs_more_conversation=True
            )
        
        # Continue conversation - no clear intent or insufficient confidence
        return AgentSelection(
            selected_agent=AgentType.VOICE_COMPANION,
            agent_name="General Conversation",
            confidence=intent_result.confidence,
            reasoning=f"Intent: {normalized_intent}, Confidence: {intent_result.confidence:.1%} - continuing conversation",
            should_route=False,
            needs_more_conversation=True
        )
