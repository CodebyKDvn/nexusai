"""Core framework for Nexus AI agent system."""

from nexus.core.agent import Agent, AgentId, AgentRole
from nexus.core.loop import AgentLoop
from nexus.core.message import Message, MessageBus, MessageType
from nexus.core.registry import AgentRegistry
from nexus.core.tool import Tool, ToolResult

__all__ = [
    "Agent",
    "AgentId",
    "AgentLoop",
    "AgentRegistry",
    "AgentRole",
    "Message",
    "MessageBus",
    "MessageType",
    "Tool",
    "ToolResult",
]
