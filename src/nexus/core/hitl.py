"""Human-in-the-Loop (HITL) — approval gates and visual diff preview.

Provides configurable approval gates that pause agent execution for human
review before high-risk actions: large git commits, sensitive file writes,
deployments, and configuration changes.
"""

from __future__ import annotations

import difflib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class ApprovalStatus(StrEnum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"


class GateType(StrEnum):
    """Categories of operations requiring approval."""

    GIT_COMMIT = "git_commit"
    FILE_WRITE = "file_write"
    DEPLOY = "deploy"
    CONFIG_CHANGE = "config_change"
    DESTRUCTIVE = "destructive"
    EXTERNAL_API = "external_api"


# Sensitivity levels
class SensitivityLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Patterns for sensitive file paths
SENSITIVE_PATTERNS: list[tuple[str, SensitivityLevel]] = [
    (".env", SensitivityLevel.CRITICAL),
    ("secret", SensitivityLevel.CRITICAL),
    ("credential", SensitivityLevel.CRITICAL),
    ("password", SensitivityLevel.CRITICAL),
    (".key", SensitivityLevel.CRITICAL),
    (".pem", SensitivityLevel.CRITICAL),
    ("config.yaml", SensitivityLevel.HIGH),
    ("config.json", SensitivityLevel.HIGH),
    ("Dockerfile", SensitivityLevel.HIGH),
    ("docker-compose", SensitivityLevel.HIGH),
    ("Makefile", SensitivityLevel.MEDIUM),
    ("pyproject.toml", SensitivityLevel.MEDIUM),
    ("package.json", SensitivityLevel.MEDIUM),
    (".github/", SensitivityLevel.MEDIUM),
    (".gitlab-ci", SensitivityLevel.MEDIUM),
]


@dataclass
class DiffPreview:
    """Visual diff of a proposed change."""

    file_path: str
    original: str
    proposed: str
    diff_lines: list[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    sensitivity: SensitivityLevel = SensitivityLevel.LOW

    def __post_init__(self) -> None:
        if not self.diff_lines:
            self.diff_lines = list(
                difflib.unified_diff(
                    self.original.splitlines(keepends=True),
                    self.proposed.splitlines(keepends=True),
                    fromfile=f"a/{self.file_path}",
                    tofile=f"b/{self.file_path}",
                    lineterm="",
                )
            )
            self.additions = sum(
                1 for line in self.diff_lines if line.startswith("+") and not line.startswith("+++")
            )
            self.deletions = sum(
                1 for line in self.diff_lines if line.startswith("-") and not line.startswith("---")
            )

    @property
    def diff_text(self) -> str:
        return "\n".join(self.diff_lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "additions": self.additions,
            "deletions": self.deletions,
            "sensitivity": self.sensitivity.value,
            "diff": self.diff_text,
        }


@dataclass
class ApprovalRequest:
    """A request for human approval before executing an action."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    gate_type: GateType = GateType.FILE_WRITE
    description: str = ""
    agent_id: str = ""
    sensitivity: SensitivityLevel = SensitivityLevel.LOW
    diffs: list[DiffPreview] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer: str = ""
    review_comment: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    resolved_at: str = ""

    def approve(self, reviewer: str = "user", comment: str = "") -> None:
        self.status = ApprovalStatus.APPROVED
        self.reviewer = reviewer
        self.review_comment = comment
        self.resolved_at = datetime.now(UTC).isoformat()

    def reject(self, reviewer: str = "user", comment: str = "") -> None:
        self.status = ApprovalStatus.REJECTED
        self.reviewer = reviewer
        self.review_comment = comment
        self.resolved_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "gate_type": self.gate_type.value,
            "description": self.description,
            "agent_id": self.agent_id,
            "sensitivity": self.sensitivity.value,
            "diffs": [d.to_dict() for d in self.diffs],
            "status": self.status.value,
            "reviewer": self.reviewer,
            "review_comment": self.review_comment,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


@dataclass
class GatePolicy:
    """Policy for when approval is required."""

    gate_type: GateType
    min_sensitivity: SensitivityLevel = SensitivityLevel.LOW
    enabled: bool = True
    auto_approve_below: SensitivityLevel = SensitivityLevel.LOW

    def requires_approval(self, sensitivity: SensitivityLevel) -> bool:
        if not self.enabled:
            return False
        level_order = list(SensitivityLevel)
        return level_order.index(sensitivity) >= level_order.index(self.min_sensitivity)


DEFAULT_POLICIES: list[GatePolicy] = [
    GatePolicy(
        gate_type=GateType.GIT_COMMIT,
        min_sensitivity=SensitivityLevel.MEDIUM,
        auto_approve_below=SensitivityLevel.LOW,
    ),
    GatePolicy(
        gate_type=GateType.FILE_WRITE,
        min_sensitivity=SensitivityLevel.HIGH,
        auto_approve_below=SensitivityLevel.MEDIUM,
    ),
    GatePolicy(
        gate_type=GateType.DEPLOY,
        min_sensitivity=SensitivityLevel.LOW,
    ),
    GatePolicy(
        gate_type=GateType.CONFIG_CHANGE,
        min_sensitivity=SensitivityLevel.MEDIUM,
    ),
    GatePolicy(
        gate_type=GateType.DESTRUCTIVE,
        min_sensitivity=SensitivityLevel.LOW,
    ),
    GatePolicy(
        gate_type=GateType.EXTERNAL_API,
        min_sensitivity=SensitivityLevel.HIGH,
    ),
]


class ApprovalGateManager:
    """Manages approval gates for HITL workflows.

    Tracks pending requests, evaluates policies, and maintains an
    audit log of all approval decisions.
    """

    def __init__(
        self,
        policies: list[GatePolicy] | None = None,
        auto_approve: bool = False,
    ) -> None:
        self._policies: dict[GateType, GatePolicy] = {}
        for p in (policies or DEFAULT_POLICIES):
            self._policies[p.gate_type] = p
        self._pending: dict[str, ApprovalRequest] = {}
        self._history: list[ApprovalRequest] = []
        self._auto_approve = auto_approve
        self._callbacks: list[Any] = []

    def register_callback(self, callback: Any) -> None:
        """Register a callback for approval events (for UI/WebSocket)."""
        self._callbacks.append(callback)

    @property
    def pending_requests(self) -> list[ApprovalRequest]:
        return list(self._pending.values())

    @property
    def history(self) -> list[ApprovalRequest]:
        return list(self._history)

    def classify_sensitivity(self, file_path: str) -> SensitivityLevel:
        """Determine sensitivity level of a file path."""
        path_lower = file_path.lower()
        for pattern, level in SENSITIVE_PATTERNS:
            if pattern in path_lower:
                return level
        return SensitivityLevel.LOW

    def check_gate(
        self,
        gate_type: GateType,
        description: str,
        agent_id: str = "",
        sensitivity: SensitivityLevel | None = None,
        diffs: list[DiffPreview] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        """Check if an action needs approval, creating a request if so.

        Returns an ApprovalRequest. If ``auto_approve`` is set or the policy
        doesn't require approval, the request is pre-approved.
        """
        if sensitivity is None:
            if diffs:
                sensitivity = max(
                    (d.sensitivity for d in diffs),
                    key=lambda s: list(SensitivityLevel).index(s),
                    default=SensitivityLevel.LOW,
                )
            else:
                sensitivity = SensitivityLevel.LOW

        request = ApprovalRequest(
            gate_type=gate_type,
            description=description,
            agent_id=agent_id,
            sensitivity=sensitivity,
            diffs=diffs or [],
            metadata=metadata or {},
        )

        policy = self._policies.get(gate_type)
        if policy is None or not policy.requires_approval(sensitivity):
            request.approve(reviewer="policy", comment="Below approval threshold")
            self._history.append(request)
            return request

        if self._auto_approve:
            request.approve(reviewer="auto", comment="Auto-approve enabled")
            self._history.append(request)
            return request

        self._pending[request.request_id] = request
        logger.info(
            "Approval required: %s [%s] sensitivity=%s",
            gate_type.value,
            request.request_id,
            sensitivity.value,
        )

        for cb in self._callbacks:
            try:
                cb(request)
            except Exception:
                logger.exception("Approval callback failed")

        return request

    def resolve(
        self,
        request_id: str,
        approved: bool,
        reviewer: str = "user",
        comment: str = "",
    ) -> ApprovalRequest | None:
        """Resolve a pending approval request."""
        request = self._pending.pop(request_id, None)
        if request is None:
            return None

        if approved:
            request.approve(reviewer=reviewer, comment=comment)
        else:
            request.reject(reviewer=reviewer, comment=comment)

        self._history.append(request)
        logger.info(
            "Approval %s: %s by %s",
            request.status.value,
            request_id,
            reviewer,
        )
        return request

    def create_file_diff(
        self,
        file_path: str,
        original: str,
        proposed: str,
    ) -> DiffPreview:
        """Create a diff preview with auto-detected sensitivity."""
        sensitivity = self.classify_sensitivity(file_path)
        return DiffPreview(
            file_path=file_path,
            original=original,
            proposed=proposed,
            sensitivity=sensitivity,
        )

    def summary(self) -> dict[str, Any]:
        """Return summary of gate activity."""
        return {
            "pending": len(self._pending),
            "total_reviewed": len(self._history),
            "approved": sum(1 for r in self._history if r.status == ApprovalStatus.APPROVED),
            "rejected": sum(1 for r in self._history if r.status == ApprovalStatus.REJECTED),
            "policies": {
                gt.value: {"enabled": p.enabled, "min_sensitivity": p.min_sensitivity.value}
                for gt, p in self._policies.items()
            },
        }
