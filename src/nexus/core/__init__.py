"""Core framework for Nexus AI agent system."""

from nexus.core.agent import Agent, AgentId, AgentRole
from nexus.core.crew import CrewAssembler, CrewAssignment, TaskCategory
from nexus.core.evaluation import MetricsLogger, SelfEvaluator
from nexus.core.hitl import ApprovalGateManager, ApprovalRequest, GateType
from nexus.core.loop import AgentLoop
from nexus.core.message import Message, MessageBus, MessageType
from nexus.core.observability import Tracer
from nexus.core.parallel import ParallelExecutionEngine, ParallelResult, ParallelTask
from nexus.core.recovery import RecoveryManager, RetryPolicy
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
    "ApprovalGateManager",
    "ApprovalRequest",
    "CheckpointManager",
    "CrewAssembler",
    "CrewAssignment",
    "GateType",
    "Message",
    "MessageBus",
    "MessageType",
    "MetricsLogger",
    "ParallelExecutionEngine",
    "ParallelResult",
    "ParallelTask",
    "RecoveryManager",
    "RetryPolicy",
    "SelfEvaluator",
    "TaskCategory",
    "TaskGraph",
    "TaskState",
    "TaskStatus",
    "Tool",
    "ToolResult",
    "Tracer",
    "WorkflowEngine",
    "WorkflowGraph",
    "WorkflowPhase",
]
