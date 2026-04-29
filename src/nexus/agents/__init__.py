"""Specialized agents for the Nexus AI dev team."""

from nexus.agents.backend_developer import BackendDeveloperAgent
from nexus.agents.critic import CriticAgent
from nexus.agents.debugger import DebuggerAgent
from nexus.agents.frontend_developer import FrontendDeveloperAgent
from nexus.agents.memory_agent import MemoryAgentImpl
from nexus.agents.orchestrator import OrchestratorAgent
from nexus.agents.planner import PlannerAgent
from nexus.agents.qa import QAAgent
from nexus.agents.research import ResearchAgent
from nexus.agents.tool_executor import ToolExecutorAgent

__all__ = [
    "BackendDeveloperAgent",
    "CriticAgent",
    "DebuggerAgent",
    "FrontendDeveloperAgent",
    "MemoryAgentImpl",
    "OrchestratorAgent",
    "PlannerAgent",
    "QAAgent",
    "ResearchAgent",
    "ToolExecutorAgent",
]
