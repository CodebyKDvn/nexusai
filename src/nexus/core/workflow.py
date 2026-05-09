"""Hierarchical Graph Workflow — LangGraph/AutoGen-inspired supervisor pattern.

Replaces the linear AgentLoop with a phase-based graph where the
Orchestrator acts as supervisor, creating dynamic sub-graphs per phase
(Plan → Design → Code → Test → Deploy).

Each phase is a node in the workflow graph.  The supervisor decides
which phase to enter next based on the current state.  Within each
phase, a sub-graph of agents collaborates to produce output.
"""

from __future__ import annotations

import contextlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from nexus.core.message import Message, MessageType
from nexus.core.parallel import ParallelExecutionEngine, ParallelTask
from nexus.core.state import TaskGraph, TaskStatus

if TYPE_CHECKING:
    from nexus.core.registry import AgentRegistry

logger = logging.getLogger(__name__)


class WorkflowPhase(StrEnum):
    """High-level phases in a development workflow."""

    PLAN = "plan"
    DESIGN = "design"
    CODE = "code"
    TEST = "test"
    REVIEW = "review"
    DEPLOY = "deploy"
    COMPLETE = "complete"


# Default agent assignments for each phase
PHASE_AGENTS: dict[WorkflowPhase, list[str]] = {
    WorkflowPhase.PLAN: ["planner"],
    WorkflowPhase.DESIGN: ["ux_ui_designer"],
    WorkflowPhase.CODE: ["frontend_developer", "backend_developer"],
    WorkflowPhase.TEST: ["qa", "debugger"],
    WorkflowPhase.REVIEW: ["critic"],
    WorkflowPhase.DEPLOY: ["backend_developer"],
}

# Default phase ordering — the supervisor can skip phases dynamically
DEFAULT_PHASE_ORDER: list[WorkflowPhase] = [
    WorkflowPhase.PLAN,
    WorkflowPhase.DESIGN,
    WorkflowPhase.CODE,
    WorkflowPhase.TEST,
    WorkflowPhase.REVIEW,
]


@dataclass
class PhaseResult:
    """Result of executing a single workflow phase."""

    phase: WorkflowPhase
    outputs: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    success: bool = True
    skipped: bool = False


@dataclass
class WorkflowEdge:
    """An edge in the workflow graph connecting two phases."""

    from_phase: WorkflowPhase
    to_phase: WorkflowPhase
    condition: str = ""  # Human-readable condition description


@dataclass
class WorkflowNode:
    """A node in the workflow graph representing a phase."""

    phase: WorkflowPhase
    agents: list[str] = field(default_factory=list)
    parallel: bool = False  # Whether agents in this phase run in parallel
    required: bool = True  # Whether this phase can be skipped
    max_iterations: int = 3


class WorkflowGraph:
    """A directed graph of workflow phases with conditional edges.

    The Orchestrator (supervisor) walks this graph, executing phases
    and deciding the next phase based on results.
    """

    def __init__(self) -> None:
        self._nodes: dict[WorkflowPhase, WorkflowNode] = {}
        self._edges: list[WorkflowEdge] = []
        self._adjacency: dict[WorkflowPhase, list[WorkflowPhase]] = {}

    def add_node(
        self,
        phase: WorkflowPhase,
        agents: list[str] | None = None,
        *,
        parallel: bool = False,
        required: bool = True,
        max_iterations: int = 3,
    ) -> WorkflowNode:
        """Add a phase node to the graph."""
        node = WorkflowNode(
            phase=phase,
            agents=PHASE_AGENTS.get(phase, []) if agents is None else agents,
            parallel=parallel,
            required=required,
            max_iterations=max_iterations,
        )
        self._nodes[phase] = node
        return node

    def add_edge(
        self,
        from_phase: WorkflowPhase,
        to_phase: WorkflowPhase,
        condition: str = "",
    ) -> WorkflowEdge:
        """Add a directed edge between phases."""
        edge = WorkflowEdge(
            from_phase=from_phase,
            to_phase=to_phase,
            condition=condition,
        )
        self._edges.append(edge)
        self._adjacency.setdefault(from_phase, []).append(to_phase)
        return edge

    def get_node(self, phase: WorkflowPhase) -> WorkflowNode | None:
        return self._nodes.get(phase)

    def get_successors(self, phase: WorkflowPhase) -> list[WorkflowPhase]:
        return self._adjacency.get(phase, [])

    def get_entry_phase(self) -> WorkflowPhase | None:
        """Return the first phase (node with no incoming edges)."""
        has_incoming = {e.to_phase for e in self._edges}
        for phase in self._nodes:
            if phase not in has_incoming:
                return phase
        return next(iter(self._nodes), None)

    @property
    def nodes(self) -> dict[WorkflowPhase, WorkflowNode]:
        return dict(self._nodes)

    @property
    def edges(self) -> list[WorkflowEdge]:
        return list(self._edges)

    @classmethod
    def create_default(cls) -> WorkflowGraph:
        """Create the default Plan→Design→Code→Test→Review workflow."""
        graph = cls()
        graph.add_node(WorkflowPhase.PLAN, parallel=False)
        graph.add_node(WorkflowPhase.DESIGN, parallel=False, required=False)
        graph.add_node(WorkflowPhase.CODE, parallel=True)
        graph.add_node(WorkflowPhase.TEST, parallel=True)
        graph.add_node(WorkflowPhase.REVIEW, parallel=False)

        graph.add_edge(WorkflowPhase.PLAN, WorkflowPhase.DESIGN)
        graph.add_edge(WorkflowPhase.PLAN, WorkflowPhase.CODE, condition="no design needed")
        graph.add_edge(WorkflowPhase.DESIGN, WorkflowPhase.CODE)
        graph.add_edge(WorkflowPhase.CODE, WorkflowPhase.TEST)
        graph.add_edge(WorkflowPhase.TEST, WorkflowPhase.REVIEW)
        graph.add_edge(WorkflowPhase.REVIEW, WorkflowPhase.CODE, condition="revisions needed")

        return graph


@dataclass
class WorkflowState:
    """Runtime state of a workflow execution."""

    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    current_phase: WorkflowPhase | None = None
    completed_phases: list[str] = field(default_factory=list)
    phase_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    iteration: int = 0
    max_iterations: int = 30
    completed: bool = False
    errors: list[str] = field(default_factory=list)


class WorkflowEngine:
    """Executes a workflow graph, with the Orchestrator as supervisor.

    This replaces the flat ``AgentLoop`` for complex tasks that benefit
    from phased execution.  Simple tasks still use the linear loop.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        graph: WorkflowGraph | None = None,
        task_graph: TaskGraph | None = None,
        max_iterations: int = 30,
    ) -> None:
        self.registry = registry
        self.graph = graph or WorkflowGraph.create_default()
        self.task_graph = task_graph or TaskGraph()
        self.max_iterations = max_iterations
        self._parallel = ParallelExecutionEngine(
            registry, task_graph=self.task_graph,
        )
        self._state = WorkflowState(max_iterations=max_iterations)

    @property
    def state(self) -> WorkflowState:
        return self._state

    def run(self, task: str, context: str = "") -> WorkflowState:
        """Execute the full workflow for a given task."""
        self._state = WorkflowState(max_iterations=self.max_iterations)

        # Create root task in the graph
        root_task = self.task_graph.add_task(
            description=task,
            task_id=f"workflow-{self._state.workflow_id}",
        )
        self.task_graph.transition_task(
            root_task.task_id,
            TaskStatus.IN_PROGRESS,
            agent_id="orchestrator",
            reason="Workflow started",
        )

        entry = self.graph.get_entry_phase()
        if entry is None:
            self._state.errors.append("No entry phase in workflow graph")
            return self._state

        self._state.current_phase = entry
        accumulated_context = context

        while (
            self._state.current_phase is not None
            and self._state.iteration < self.max_iterations
            and not self._state.completed
        ):
            phase = self._state.current_phase
            self._state.iteration += 1

            logger.info(
                "Workflow %s — Phase %s (iteration %d)",
                self._state.workflow_id,
                phase.value,
                self._state.iteration,
            )

            node = self.graph.get_node(phase)
            if node is None:
                self._state.errors.append(f"Phase {phase} not found in graph")
                break

            phase_result = self._execute_phase(node, task, accumulated_context)
            self._state.phase_results[phase.value] = {
                "outputs": phase_result.outputs,
                "errors": phase_result.errors,
                "success": phase_result.success,
                "skipped": phase_result.skipped,
            }
            self._state.completed_phases.append(phase.value)

            # Accumulate context from phase outputs
            for output in phase_result.outputs:
                result_str = str(output.get("result", ""))
                if result_str:
                    accumulated_context += f"\n\n[{phase.value} output]: {result_str[:500]}"

            # Determine next phase
            next_phase = self._decide_next_phase(phase, phase_result)
            self._state.current_phase = next_phase

            if next_phase is None:
                self._state.completed = True

        # Complete root task
        final_status = TaskStatus.COMPLETED if self._state.completed else TaskStatus.FAILED
        with contextlib.suppress(Exception):
            self.task_graph.transition_task(
                root_task.task_id,
                final_status,
                agent_id="orchestrator",
                reason="Workflow finished",
            )

        return self._state

    def _execute_phase(
        self,
        node: WorkflowNode,
        task: str,
        context: str,
    ) -> PhaseResult:
        """Execute all agents in a phase, optionally in parallel."""
        result = PhaseResult(phase=node.phase)

        if not node.agents:
            result.skipped = True
            return result

        available_agents = [a for a in node.agents if self.registry.get(a) is not None]
        if not available_agents:
            result.skipped = True
            result.errors.append(f"No available agents for phase {node.phase}")
            return result

        if node.parallel and len(available_agents) > 1:
            return self._execute_phase_parallel(
                node.phase, available_agents, task, context,
            )

        return self._execute_phase_sequential(
            node.phase, available_agents, task, context,
        )

    def _execute_phase_sequential(
        self,
        phase: WorkflowPhase,
        agents: list[str],
        task: str,
        context: str,
    ) -> PhaseResult:
        """Execute agents one by one in a phase."""
        result = PhaseResult(phase=phase)

        for agent_id in agents:
            agent = self.registry.get(agent_id)
            if agent is None:
                continue

            msg = Message(
                sender="orchestrator",
                recipient=agent_id,
                type=MessageType.TASK_REQUEST,
                payload={
                    "task": task,
                    "context": context,
                    "phase": phase.value,
                },
            )

            try:
                response = agent.process(msg)
                if response is not None:
                    result.outputs.append(response.to_dict().get("payload", {}))
            except Exception as e:
                result.errors.append(f"{agent_id}: {e}")
                result.success = False

        return result

    def _execute_phase_parallel(
        self,
        phase: WorkflowPhase,
        agents: list[str],
        task: str,
        context: str,
    ) -> PhaseResult:
        """Execute agents in parallel within a phase."""
        result = PhaseResult(phase=phase)

        parallel_tasks: list[ParallelTask] = []
        for agent_id in agents:
            ptask = ParallelTask(
                task_id=f"{phase.value}-{agent_id}",
                agent_id=agent_id,
                message=Message(
                    sender="orchestrator",
                    recipient=agent_id,
                    type=MessageType.TASK_REQUEST,
                    payload={
                        "task": task,
                        "context": context,
                        "phase": phase.value,
                    },
                ),
            )
            parallel_tasks.append(ptask)

        p_results = self._parallel.execute(parallel_tasks)

        for pr in p_results:
            if pr.success and pr.response is not None:
                result.outputs.append(pr.response.to_dict().get("payload", {}))
            elif not pr.success:
                result.errors.append(f"{pr.agent_id}: {pr.error}")
                result.success = False

        return result

    def _decide_next_phase(
        self,
        current: WorkflowPhase,
        phase_result: PhaseResult,
    ) -> WorkflowPhase | None:
        """Decide the next phase based on results — supervisor logic."""
        successors = self.graph.get_successors(current)

        if not successors:
            return None

        # If phase failed, don't proceed to next phases
        if not phase_result.success:
            return None

        # If review phase found revisions needed, loop back to code
        if current == WorkflowPhase.REVIEW:
            for output in phase_result.outputs:
                verdict = ""
                result_val = output.get("result", {})
                if isinstance(result_val, dict):
                    verdict = result_val.get("verdict", "")
                if verdict == "revise" and WorkflowPhase.CODE in successors:
                    review_count = sum(
                        1 for p in self._state.completed_phases if p == "review"
                    )
                    if review_count < 2:
                        return WorkflowPhase.CODE
            return None  # Approved or max reviews reached

        # Route from PLAN: go to DESIGN only if the task needs it
        if current == WorkflowPhase.PLAN and len(successors) > 1:
            design_node = self.graph.get_node(WorkflowPhase.DESIGN)
            if design_node and not design_node.required and WorkflowPhase.CODE in successors:
                # Check accumulated context / task for design-related signals
                task_text = ""
                for output in phase_result.outputs:
                    task_text += str(output.get("result", ""))
                task_text = task_text.lower()
                design_keywords = [
                    r"\bdesign\b", r"\bui\b", r"\bux\b", r"\bwireframe\b",
                    r"\bmockup\b", r"\bprototype\b", r"\blayout\b",
                    r"\bvisual\b", r"\bbrand\b",
                ]
                needs_design = any(
                    re.search(kw, task_text) for kw in design_keywords
                )
                if not needs_design:
                    return WorkflowPhase.CODE
            return successors[0]

        # Default: follow the first successor
        return successors[0]

    def get_phase_summary(self) -> dict[str, Any]:
        """Return a summary of all phase results."""
        return {
            "workflow_id": self._state.workflow_id,
            "completed": self._state.completed,
            "iterations": self._state.iteration,
            "phases": self._state.phase_results,
            "errors": self._state.errors,
        }
