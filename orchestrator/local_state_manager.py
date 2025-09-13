#orchestrator/local_state_manager.py
import logging
import asyncio
from typing import Dict, List, Optional, Any, Literal, Union
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
import httpx
from common.models import Conversation, AgentResult, Task, Checkpoint

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@dataclass
class AgentInfo:
    """Simple agent information with essential fields"""
    name: str
    agent_type: Literal["sync", "async"] = "sync"
    status: str = "pending"  # pending, ready, calling, completed, failed
    call_at: Optional[datetime] = None  # When to call this agent
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)


class AgentTracker:
    """
    Enhanced tracker for support agents with status and timing control.
    Keeps only essential fields for practical use.
    """

    def __init__(self):
        self.agents: Dict[str, AgentInfo] = {}

    def add_agents(self,
                  agents: List[str],
                  agent_type: Literal["sync", "async"] = "sync",
                  status: str = "pending",
                  call_at: Optional[datetime] = None):
        """Add multiple agents to tracking list"""
        print(f"Adding agents: {agents}, type: {agent_type}")
        for agent in agents:
            self.add_agent(agent, agent_type, status, call_at)
        print(f"Current agents: {list(self.agents.keys())}")

    def add_agent(self,
                 agent: str,
                 agent_type: Literal["sync", "async"] = "sync",
                 status: str = "pending",
                 call_at: Optional[datetime] = None):
        """Add single agent with basic configuration"""

        agent_info = AgentInfo(
            name=agent,
            agent_type=agent_type,
            status=status,
            call_at=call_at
        )

        self.agents[agent] = agent_info
        logger.info(f"Added agent {agent} with status {status}")

    def update_status(self, agent: str, status: str):
        """Update agent status"""
        if agent in self.agents:
            self.agents[agent].status = status
            self.agents[agent].last_updated = datetime.now()
            logger.info(f"Updated agent {agent} status to {status}")
            return True
        return False

    def set_call_time(self, agent: str, call_at: datetime):
        """Set when agent should be called"""
        if agent in self.agents:
            self.agents[agent].call_at = call_at
            self.agents[agent].last_updated = datetime.now()
            return True
        return False

    def get_ready_agents(self, agent_type: Optional[Literal["sync", "async"]] = None) -> List[AgentInfo]:
        """Get agents that are ready to be called"""
        ready_agents = []
        now = datetime.now()

        for agent_info in self.agents.values():
            # Filter by type if specified
            if agent_type and agent_info.agent_type != agent_type:
                continue

            # Check if agent is ready (both pending and ready status)
            if agent_info.status in ["pending", "ready", "completed"]:
                # If call_at is set, check if it's time
                if agent_info.call_at is None or now >= agent_info.call_at:
                    ready_agents.append(agent_info)

        return ready_agents

    def mark_calling(self, agent: str) -> bool:
        """Mark agent as currently being called"""
        return self.update_status(agent, "calling")

    def mark_ready(self, agent: str) -> bool:
        """Mark agent as ready to be called"""
        return self.update_status(agent, "ready")

    def mark_completed(self, agent: str) -> bool:
        """Mark agent as completed"""
        return self.update_status(agent, "completed")

    def mark_failed(self, agent: str) -> bool:
        """Mark agent as failed"""
        return self.update_status(agent, "failed")

    def mark_processed(self, agent: str) -> bool:
        """Mark an agent as processed (called and completed successfully)"""
        return self.update_status(agent, "processed")

    def remove_agent(self, agent: str) -> bool:
        """Remove specific agent from tracking"""
        if agent in self.agents:
            del self.agents[agent]
            logger.info(f"Removed agent {agent} from tracker")
            return True
        return False

    def get_status(self, agent: str) -> Optional[str]:
        """Get current status of specific agent"""
        agent_info = self.agents.get(agent)
        return agent_info.status if agent_info else None

    def get_agents_by_status(self, status: str) -> List[AgentInfo]:
        """Get all agents with specific status"""
        return [info for info in self.agents.values() if info.status == status]

    def get_sync_agents(self) -> List[str]:
        """Get list of sync agent names (for backward compatibility)"""
        return [info.name for info in self.agents.values()
                if info.agent_type == "sync" and info.status not in ["failed"]]

    def get_async_agents(self) -> List[str]:
        """Get list of async agent names (for backward compatibility)"""
        return [info.name for info in self.agents.values()
                if info.agent_type == "async" and info.status not in ["failed"]]

    def get_active_agents(self) -> Dict[str, AgentInfo]:
        """Get all agents that are still active (not completed, failed, or processed)"""
        return {name: info for name, info in self.agents.items()
                if info.status not in ["failed", "processed"]}

    def cleanup_completed_agents(self) -> List[str]:
        """Remove all completed agents and return their names"""
        completed_agents = []
        agents_to_remove = []

        for name, info in self.agents.items():
            if info.status == "completed":
                completed_agents.append(name)
                agents_to_remove.append(name)

        for agent in agents_to_remove:
            self.remove_agent(agent)

        return completed_agents

    def has_agent(self, agent: str) -> bool:
        """Check if agent exists in tracker"""
        return agent in self.agents

    def is_agent_completed_or_failed(self, agent: str) -> bool:
        """Check if agent is completed or failed"""
        if agent not in self.agents:
            return False
        return self.agents[agent].status in ["completed", "failed", "processed"]

    def get_agent_info(self, agent: str) -> Optional[AgentInfo]:
        """Get complete agent information"""
        return self.agents.get(agent)

    def __len__(self) -> int:
        """Return total number of tracked agents"""
        return len(self.agents)

    def __contains__(self, agent: str) -> bool:
        """Check if agent is being tracked"""
        return agent in self.agents

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all agents and their statuses"""
        summary = {
            "total_agents": len(self.agents),
            "by_status": {},
            "by_type": {"sync": 0, "async": 0},
            "agents": []
        }

        status_counts = {}
        for info in self.agents.values():
            # Count by status
            status_counts[info.status] = status_counts.get(info.status, 0) + 1

            # Count by type
            summary["by_type"][info.agent_type] += 1

            # Add agent details
            summary["agents"].append({
                "name": info.name,
                "type": info.agent_type,
                "status": info.status,
                "created_at": info.created_at.isoformat(),
                "last_updated": info.last_updated.isoformat()
            })

        summary["by_status"] = status_counts
        return summary

    def clear_all(self):
        """Clear all agents from tracker"""
        cleared_count = len(self.agents)
        self.agents.clear()
        logger.info(f"Cleared {cleared_count} agents from tracker")
