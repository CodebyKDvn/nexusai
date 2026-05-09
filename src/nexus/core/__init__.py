"""Core framework for Nexus AI agent system."""

from nexus.core.agent import Agent, AgentId, AgentRole
from nexus.core.crew import CrewAssembler, CrewAssignment, TaskCategory
from nexus.core.loop import AgentLoop
from nexus.core.message import Message, MessageBus, MessageType
from nexus.core.parallel import ParallelExecutionEngine, ParallelResult, ParallelTask
from nexus.core.registry import AgentRegistry
from nexus.core.state import (
    CheckpointManager,
    TaskGraph,
    TaskState,
    TaskStatus,
)
from nexus.core.tool import Tool, ToolResult
from nexus.core.workflow import WorkflowEngine, WorkflowGraph, WorkflowPhase

__all__ = [
    "Agent",
    "AgentId",
    "AgentLoop",
    "AgentRegistry",
    "AgentRole",
    "CheckpointManager",
    "CrewAssembler",
    "CrewAssignment",
    "Message",
    "MessageBus",
    "MessageType",
    "ParallelExecutionEngine",
    "ParallelResult",
    "ParallelTask",
    "TaskCategory",
    "TaskGraph",
    "TaskState",
    "TaskStatus",
    "Tool",
    "ToolResult",
    "WorkflowEngine",
    "WorkflowGraph",
    "WorkflowPhase",
]
