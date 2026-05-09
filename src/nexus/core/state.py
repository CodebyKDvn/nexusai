"""Task state machine and checkpoint management.

Provides persistent state for tasks so work can survive crashes, pauses,
and be resumed later.  Every state transition is recorded and checkpoints
are written to ``.nexus_state/`` as JSON files.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TaskStatus(StrEnum):
    """Lifecycle states a task can be in."""

    PENDING = "pending"
    PLANNING = "planning"
    DELEGATED = "delegated"
    IN_PROGRESS = "in_progress"
    REVIEWING = "reviewing"
    REVISING = "revising"
    BLOCKED = "blocked"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


# Valid transitions: from_status -> {allowed next statuses}
VALID_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({
        TaskStatus.PLANNING, TaskStatus.DELEGATED, TaskStatus.IN_PROGRESS,
        TaskStatus.COMPLETED, TaskStatus.FAILED,
    }),
    TaskStatus.PLANNING: frozenset({
        TaskStatus.DELEGATED, TaskStatus.IN_PROGRESS,
        TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.BLOCKED,
    }),
    TaskStatus.DELEGATED: frozenset({
        TaskStatus.IN_PROGRESS, TaskStatus.REVIEWING,
        TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.BLOCKED,
    }),
    TaskStatus.IN_PROGRESS: frozenset({
        TaskStatus.REVIEWING, TaskStatus.COMPLETED,
        TaskStatus.FAILED, TaskStatus.PAUSED, TaskStatus.BLOCKED,
    }),
    TaskStatus.REVIEWING: frozenset({
        TaskStatus.REVISING, TaskStatus.COMPLETED, TaskStatus.FAILED,
    }),
    TaskStatus.REVISING: frozenset({
        TaskStatus.REVIEWING, TaskStatus.IN_PROGRESS,
        TaskStatus.COMPLETED, TaskStatus.FAILED,
    }),
    TaskStatus.BLOCKED: frozenset({
        TaskStatus.PENDING, TaskStatus.IN_PROGRESS,
        TaskStatus.FAILED, TaskStatus.PAUSED,
    }),
    TaskStatus.PAUSED: frozenset({
        TaskStatus.PENDING, TaskStatus.IN_PROGRESS,
        TaskStatus.PLANNING, TaskStatus.FAILED,
    }),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset({TaskStatus.PENDING}),
}


@dataclass
class StateTransition:
    """A single state transition record."""

    from_status: str
    to_status: str
    timestamp: str
    agent_id: str = ""
    reason: str = ""


@dataclass
class TaskState:
    """Full state of a single task."""

    task_id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: str = ""
    parent_task_id: str = ""
    subtask_ids: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    result: Any = None
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    history: list[dict[str, str]] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3

    def transition(
        self,
        new_status: TaskStatus,
        *,
        agent_id: str = "",
        reason: str = "",
    ) -> None:
        """Transition to a new status, validating the transition is legal."""
        allowed = VALID_TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition {self.task_id} from {self.status} to {new_status}. "
                f"Allowed: {sorted(allowed)}"
            )
        record = StateTransition(
            from_status=self.status.value,
            to_status=new_status.value,
            timestamp=datetime.now(UTC).isoformat(),
            agent_id=agent_id,
            reason=reason,
        )
        self.history.append(asdict(record))
        self.status = new_status
        self.updated_at = datetime.now(UTC).isoformat()

    @property
    def is_terminal(self) -> bool:
        return self.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}

    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskState:
        data = dict(data)
        data["status"] = TaskStatus(data["status"])
        return cls(**data)


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""


@dataclass
class Checkpoint:
    """A snapshot of the entire workflow state at a point in time."""

    checkpoint_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    workflow_id: str = ""
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    iteration: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Checkpoint:
        return cls(**data)


class CheckpointManager:
    """Persists and restores workflow checkpoints to/from disk.

    Checkpoints are stored as JSON files under ``state_dir``
    (default: ``.nexus_state/``).
    """

    def __init__(self, state_dir: str | Path = ".nexus_state") -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._workflow_id = str(uuid.uuid4())[:12]

    @property
    def workflow_id(self) -> str:
        return self._workflow_id

    def save(
        self,
        tasks: dict[str, TaskState],
        iteration: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> Checkpoint:
        """Save current state as a checkpoint."""
        cp = Checkpoint(
            workflow_id=self._workflow_id,
            tasks={tid: t.to_dict() for tid, t in tasks.items()},
            iteration=iteration,
            metadata=metadata or {},
        )
        filepath = self.state_dir / f"{self._workflow_id}_{cp.checkpoint_id}.json"
        filepath.write_text(json.dumps(cp.to_dict(), indent=2, default=str))
        logger.info("Checkpoint saved: %s", filepath.name)
        return cp

    def load_latest(self, workflow_id: str | None = None) -> Checkpoint | None:
        """Load the most recent checkpoint for a workflow."""
        wid = workflow_id or self._workflow_id
        candidates = sorted(
            self.state_dir.glob(f"{wid}_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            return None
        latest = candidates[-1]
        data = json.loads(latest.read_text())
        logger.info("Loaded checkpoint: %s", latest.name)
        return Checkpoint.from_dict(data)

    def restore_tasks(self, checkpoint: Checkpoint) -> dict[str, TaskState]:
        """Restore ``TaskState`` objects from a checkpoint."""
        return {
            tid: TaskState.from_dict(tdata)
            for tid, tdata in checkpoint.tasks.items()
        }

    def list_checkpoints(self, workflow_id: str | None = None) -> list[str]:
        """List checkpoint IDs for a workflow."""
        wid = workflow_id or self._workflow_id
        return [
            p.stem.split("_", 1)[1] if "_" in p.stem else p.stem
            for p in sorted(self.state_dir.glob(f"{wid}_*.json"))
        ]

    def cleanup(self, workflow_id: str | None = None, keep: int = 5) -> int:
        """Remove old checkpoints, keeping the most recent ``keep``."""
        wid = workflow_id or self._workflow_id
        candidates = sorted(
            self.state_dir.glob(f"{wid}_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        to_remove = candidates[:-keep] if len(candidates) > keep else []
        for p in to_remove:
            p.unlink()
        return len(to_remove)


class TaskGraph:
    """Manages a directed acyclic graph of tasks with dependency tracking."""

    def __init__(self, checkpoint_mgr: CheckpointManager | None = None) -> None:
        self._tasks: dict[str, TaskState] = {}
        self._checkpoint = checkpoint_mgr or CheckpointManager()
        self._iteration = 0

    @property
    def tasks(self) -> dict[str, TaskState]:
        return dict(self._tasks)

    def add_task(
        self,
        description: str,
        *,
        task_id: str | None = None,
        parent_id: str = "",
        dependencies: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskState:
        """Create and register a new task."""
        tid = task_id or f"task-{uuid.uuid4().hex[:8]}"
        task = TaskState(
            task_id=tid,
            description=description,
            parent_task_id=parent_id,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )
        self._tasks[tid] = task

        if parent_id and parent_id in self._tasks:
            self._tasks[parent_id].subtask_ids.append(tid)

        return task

    def get_task(self, task_id: str) -> TaskState | None:
        return self._tasks.get(task_id)

    def transition_task(
        self,
        task_id: str,
        new_status: TaskStatus,
        *,
        agent_id: str = "",
        reason: str = "",
        auto_checkpoint: bool = True,
    ) -> TaskState:
        """Transition a task and optionally auto-save a checkpoint."""
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"Task {task_id} not found")

        task.transition(new_status, agent_id=agent_id, reason=reason)

        if auto_checkpoint and new_status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.PAUSED,
        }:
            self.checkpoint()

        return task

    def get_ready_tasks(self) -> list[TaskState]:
        """Return tasks whose dependencies are all completed."""
        ready: list[TaskState] = []
        for task in self._tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            deps_met = all(
                self._tasks.get(dep_id) is not None
                and self._tasks[dep_id].status == TaskStatus.COMPLETED
                for dep_id in task.dependencies
            )
            if deps_met:
                ready.append(task)
        return ready

    def get_tasks_by_status(self, status: TaskStatus) -> list[TaskState]:
        return [t for t in self._tasks.values() if t.status == status]

    def all_completed(self) -> bool:
        return all(t.is_terminal for t in self._tasks.values())

    def checkpoint(self) -> Checkpoint:
        self._iteration += 1
        return self._checkpoint.save(self._tasks, self._iteration)

    def restore(self, workflow_id: str | None = None) -> bool:
        """Restore state from the latest checkpoint. Returns True if restored."""
        cp = self._checkpoint.load_latest(workflow_id)
        if cp is None:
            return False
        self._tasks = self._checkpoint.restore_tasks(cp)
        self._iteration = cp.iteration
        return True

    def summary(self) -> dict[str, Any]:
        """Return a status summary of all tasks."""
        counts: dict[str, int] = {}
        for task in self._tasks.values():
            counts[task.status.value] = counts.get(task.status.value, 0) + 1
        return {
            "total": len(self._tasks),
            "by_status": counts,
            "all_completed": self.all_completed(),
            "iteration": self._iteration,
        }
