"""Parallel Execution Engine for running independent agent tasks concurrently.

When the Orchestrator decomposes work into independent subtasks (e.g.
Frontend + Backend + Research), this engine runs them in parallel using
``concurrent.futures`` and collects the results.
"""

from __future__ import annotations

import contextlib
import logging
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from nexus.core.message import Message, MessageType
from nexus.core.state import TaskGraph, TaskStatus

if TYPE_CHECKING:
    from nexus.core.agent import Agent
    from nexus.core.registry import AgentRegistry

logger = logging.getLogger(__name__)


@dataclass
class ParallelTask:
    """A unit of work to be executed in parallel."""

    task_id: str
    agent_id: str
    message: Message
    depends_on: list[str] = field(default_factory=list)


@dataclass
class ParallelResult:
    """Result from a single parallel task execution."""

    task_id: str
    agent_id: str
    response: Message | None = None
    error: str | None = None
    duration_ms: float = 0.0
    success: bool = True


class ParallelExecutionEngine:
    """Runs independent agent tasks concurrently.

    The engine accepts a batch of ``ParallelTask`` objects, groups them by
    dependency layer, and executes each layer in parallel using a thread
    pool.  Tasks in the same layer have no dependencies on each other.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        max_workers: int = 4,
        task_graph: TaskGraph | None = None,
    ) -> None:
        self.registry = registry
        self.max_workers = max_workers
        self.task_graph = task_graph
        self._results: list[ParallelResult] = []

    @property
    def results(self) -> list[ParallelResult]:
        return list(self._results)

    def _execute_single(self, agent: Agent, message: Message) -> Message | None:
        """Execute a single agent.process() call (runs in a worker thread)."""
        return agent.process(message)

    def _build_layers(self, tasks: list[ParallelTask]) -> list[list[ParallelTask]]:
        """Topologically sort tasks into dependency layers.

        Tasks with no dependencies go in layer 0, tasks depending on
        layer-0 tasks go in layer 1, etc.
        """
        placed: set[str] = set()
        layers: list[list[ParallelTask]] = []

        remaining = list(tasks)
        while remaining:
            layer: list[ParallelTask] = []
            for t in remaining:
                if all(d in placed for d in t.depends_on):
                    layer.append(t)
            if not layer:
                # Circular dependency — force remaining into one layer
                logger.warning("Circular dependency detected; forcing remaining tasks")
                layers.append(remaining)
                break
            for t in layer:
                placed.add(t.task_id)
            layers.append(layer)
            remaining = [t for t in remaining if t.task_id not in placed]

        return layers

    def execute(self, tasks: list[ParallelTask]) -> list[ParallelResult]:
        """Execute tasks respecting dependencies, parallelising within layers."""
        self._results = []

        if not tasks:
            return []

        layers = self._build_layers(tasks)
        logger.info(
            "Parallel engine: %d tasks in %d layers", len(tasks), len(layers),
        )

        for layer_idx, layer in enumerate(layers):
            layer_results = self._execute_layer(layer, layer_idx)
            self._results.extend(layer_results)

            # Stop if any task in this layer failed
            failed = [r for r in layer_results if not r.success]
            if failed:
                logger.warning(
                    "Layer %d had %d failures — skipping remaining layers",
                    layer_idx,
                    len(failed),
                )
                break

        return self._results

    def _execute_layer(
        self, layer: list[ParallelTask], layer_idx: int,
    ) -> list[ParallelResult]:
        """Execute all tasks in a single layer concurrently."""
        results: list[ParallelResult] = []

        if len(layer) == 1:
            # No need for thread pool with a single task
            results.append(self._run_task(layer[0]))
            return results

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(layer))) as pool:
            future_to_task: dict[Future[ParallelResult], ParallelTask] = {}
            for task in layer:
                future = pool.submit(self._run_task, task)
                future_to_task[future] = task

            for future in as_completed(future_to_task):
                result = future.result()
                results.append(result)
                logger.info(
                    "Layer %d — %s/%s: %s (%.0fms)",
                    layer_idx,
                    result.agent_id,
                    result.task_id,
                    "OK" if result.success else "FAIL",
                    result.duration_ms,
                )

        return results

    def _run_task(self, task: ParallelTask) -> ParallelResult:
        """Run a single task, catching exceptions."""
        agent = self.registry.get(task.agent_id)
        if agent is None:
            return ParallelResult(
                task_id=task.task_id,
                agent_id=task.agent_id,
                error=f"Agent {task.agent_id} not found",
                success=False,
            )

        # Track in TaskGraph if available
        if self.task_graph and self.task_graph.get_task(task.task_id):
            with contextlib.suppress(Exception):
                self.task_graph.transition_task(
                    task.task_id,
                    TaskStatus.IN_PROGRESS,
                    agent_id=task.agent_id,
                    auto_checkpoint=False,
                )
        start = time.monotonic()
        try:
            response = self._execute_single(agent, task.message)
            duration = (time.monotonic() - start) * 1000

            if self.task_graph and self.task_graph.get_task(task.task_id):
                self.task_graph.transition_task(
                    task.task_id,
                    TaskStatus.COMPLETED,
                    agent_id=task.agent_id,
                    reason="Parallel execution completed",
                )

            return ParallelResult(
                task_id=task.task_id,
                agent_id=task.agent_id,
                response=response,
                duration_ms=duration,
                success=True,
            )
        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            logger.exception("Task %s failed", task.task_id)

            if self.task_graph and self.task_graph.get_task(task.task_id):
                with contextlib.suppress(Exception):
                    self.task_graph.transition_task(
                        task.task_id,
                        TaskStatus.FAILED,
                        agent_id=task.agent_id,
                        reason=str(e),
                    )

            return ParallelResult(
                task_id=task.task_id,
                agent_id=task.agent_id,
                error=str(e),
                duration_ms=duration,
                success=False,
            )

    def detect_parallelizable(
        self,
        subtasks: list[dict[str, Any]],
    ) -> list[ParallelTask]:
        """Analyze subtasks from the planner and create parallel tasks.

        Each subtask dict should have:
        - ``task``: description string
        - ``agent``: target agent_id
        - ``depends_on``: list of task IDs this depends on (optional)
        """
        parallel_tasks: list[ParallelTask] = []
        for st in subtasks:
            task_id = st.get("id", f"pt-{uuid.uuid4().hex[:8]}")
            agent_id = st.get("agent", "planner")
            depends = st.get("depends_on", [])
            msg = Message(
                sender="orchestrator",
                recipient=agent_id,
                type=MessageType.TASK_REQUEST,
                payload={
                    "task": st.get("task", ""),
                    "context": st.get("context", ""),
                },
            )
            parallel_tasks.append(
                ParallelTask(
                    task_id=task_id,
                    agent_id=agent_id,
                    message=msg,
                    depends_on=depends if isinstance(depends, list) else [],
                )
            )
        return parallel_tasks
