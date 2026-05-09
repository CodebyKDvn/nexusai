"""Advanced Error Recovery — retry policies, fallback models, and reflection loops.

Provides a multi-layered recovery strategy:
  1. **Retry** — re-run the same agent with exponential backoff.
  2. **Fallback** — switch to an alternative model if the primary fails.
  3. **Reflection** — ask the agent to reflect on its failure and try again.
  4. **Escalation** — escalate to the Orchestrator or human if all else fails.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from nexus.core.message import Message, MessageType

if TYPE_CHECKING:
    from nexus.core.registry import AgentRegistry

logger = logging.getLogger(__name__)


class RecoveryAction(StrEnum):
    """Actions the recovery system can take."""

    RETRY = "retry"
    FALLBACK = "fallback"
    REFLECT = "reflect"
    ESCALATE = "escalate"
    ABORT = "abort"


class FailureType(StrEnum):
    """Categorization of failures."""

    LLM_ERROR = "llm_error"
    TIMEOUT = "timeout"
    INVALID_OUTPUT = "invalid_output"
    TOOL_FAILURE = "tool_failure"
    AGENT_ERROR = "agent_error"
    VALIDATION_ERROR = "validation_error"
    UNKNOWN = "unknown"


@dataclass
class RetryPolicy:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay_ms: float = 500.0
    max_delay_ms: float = 30000.0
    backoff_factor: float = 2.0
    jitter: bool = True
    retryable_failures: frozenset[FailureType] = field(
        default_factory=lambda: frozenset({
            FailureType.LLM_ERROR,
            FailureType.TIMEOUT,
            FailureType.TOOL_FAILURE,
        })
    )

    def is_retryable(self, failure_type: FailureType) -> bool:
        return failure_type in self.retryable_failures

    def delay_ms(self, attempt: int) -> float:
        """Compute delay for a given attempt (0-indexed)."""
        delay = self.base_delay_ms * (self.backoff_factor ** attempt)
        return min(delay, self.max_delay_ms)


@dataclass
class FallbackConfig:
    """Configuration for model fallback behavior."""

    fallback_models: list[str] = field(default_factory=lambda: [
        "deepseek-ai/deepseek-v4-pro",
        "deepseek-ai/deepseek-v4-flash",
    ])
    max_fallback_attempts: int = 2


@dataclass
class RecoveryAttempt:
    """Record of a single recovery attempt."""

    attempt_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    action: RecoveryAction = RecoveryAction.RETRY
    attempt_number: int = 0
    agent_id: str = ""
    failure_type: FailureType = FailureType.UNKNOWN
    error_message: str = ""
    model_used: str = ""
    success: bool = False
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    reflection: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "action": self.action.value,
            "attempt_number": self.attempt_number,
            "agent_id": self.agent_id,
            "failure_type": self.failure_type.value,
            "error_message": self.error_message,
            "model_used": self.model_used,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "reflection": self.reflection,
        }


@dataclass
class RecoveryResult:
    """Overall result of a recovery process."""

    task_id: str = ""
    agent_id: str = ""
    original_error: str = ""
    attempts: list[RecoveryAttempt] = field(default_factory=list)
    final_action: RecoveryAction = RecoveryAction.ABORT
    recovered: bool = False
    response: Message | None = None
    total_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "original_error": self.original_error,
            "attempts": [a.to_dict() for a in self.attempts],
            "final_action": self.final_action.value,
            "recovered": self.recovered,
            "total_duration_ms": self.total_duration_ms,
        }


class ErrorClassifier:
    """Classifies errors into failure types for recovery policy lookup."""

    _PATTERNS: list[tuple[str, FailureType]] = [
        ("timeout", FailureType.TIMEOUT),
        ("timed out", FailureType.TIMEOUT),
        ("rate limit", FailureType.LLM_ERROR),
        ("api error", FailureType.LLM_ERROR),
        ("connection", FailureType.LLM_ERROR),
        ("model not found", FailureType.LLM_ERROR),
        ("json", FailureType.INVALID_OUTPUT),
        ("parse", FailureType.INVALID_OUTPUT),
        ("validation", FailureType.VALIDATION_ERROR),
        ("tool", FailureType.TOOL_FAILURE),
        ("command", FailureType.TOOL_FAILURE),
        ("permission", FailureType.TOOL_FAILURE),
    ]

    @classmethod
    def classify(cls, error: str | Exception) -> FailureType:
        """Classify an error into a FailureType."""
        error_str = str(error).lower()
        for pattern, ftype in cls._PATTERNS:
            if pattern in error_str:
                return ftype
        return FailureType.UNKNOWN


class ReflectionEngine:
    """Generates reflection prompts for agents to improve their next attempt.

    Implements a 2-3 layer reflection loop:
      Layer 1: What went wrong?
      Layer 2: What should change?
      Layer 3: Verify the new approach avoids the issue.
    """

    MAX_LAYERS = 3

    def generate_reflection_prompt(
        self,
        original_task: str,
        error_message: str,
        attempt_number: int,
        previous_reflections: list[str] | None = None,
    ) -> str:
        """Generate a reflection prompt based on failure context."""
        layers: list[str] = []

        # Layer 1: Diagnosis
        layers.append(
            f"REFLECTION (attempt {attempt_number}):\n"
            f"The previous attempt failed with: {error_message}\n\n"
            f"Original task: {original_task}\n\n"
            "STEP 1 — DIAGNOSE: What specifically went wrong? "
            "Identify the root cause, not just the symptom."
        )

        # Layer 2: Strategy
        if attempt_number >= 2:
            layers.append(
                "\nSTEP 2 — STRATEGY: Based on the diagnosis above, "
                "what concrete changes should be made to the approach? "
                "List specific modifications."
            )

        # Layer 3: Verification
        if attempt_number >= 3:
            layers.append(
                "\nSTEP 3 — VERIFY: Before executing, check that "
                "the new approach does not repeat any previous mistakes:\n"
                + (
                    "\n".join(
                        f"  - Attempt {i + 1}: {r}"
                        for i, r in enumerate(previous_reflections or [])
                    )
                    or "  (No previous reflections)"
                )
            )

        return "\n".join(layers)


class RecoveryManager:
    """Orchestrates error recovery across retry, fallback, reflection, and escalation.

    Usage::

        manager = RecoveryManager(registry)
        result = manager.recover(agent_id, message, error)
        if result.recovered:
            # use result.response
        else:
            # escalate or abort
    """

    def __init__(
        self,
        registry: AgentRegistry,
        retry_policy: RetryPolicy | None = None,
        fallback_config: FallbackConfig | None = None,
        max_recovery_attempts: int = 5,
    ) -> None:
        self.registry = registry
        self.retry_policy = retry_policy or RetryPolicy()
        self.fallback_config = fallback_config or FallbackConfig()
        self.reflection_engine = ReflectionEngine()
        self.max_recovery_attempts = max_recovery_attempts
        self._history: list[RecoveryResult] = []

    @property
    def history(self) -> list[RecoveryResult]:
        return list(self._history)

    def recover(
        self,
        agent_id: str,
        message: Message,
        error: str | Exception,
        task_id: str = "",
    ) -> RecoveryResult:
        """Attempt to recover from an agent failure.

        Recovery strategy:
          1. Retry with backoff (if retryable error type)
          2. Reflection loop (ask agent to re-think)
          3. Escalate to orchestrator
        """
        start = time.monotonic()
        error_str = str(error)
        failure_type = ErrorClassifier.classify(error)

        result = RecoveryResult(
            task_id=task_id,
            agent_id=agent_id,
            original_error=error_str,
        )

        logger.warning(
            "Recovery started for %s: %s (%s)",
            agent_id,
            error_str[:100],
            failure_type.value,
        )

        # Phase 1: Retry with backoff
        if self.retry_policy.is_retryable(failure_type):
            for attempt in range(self.retry_policy.max_retries):
                delay = self.retry_policy.delay_ms(attempt) / 1000.0
                time.sleep(delay)

                attempt_record = RecoveryAttempt(
                    action=RecoveryAction.RETRY,
                    attempt_number=attempt + 1,
                    agent_id=agent_id,
                    failure_type=failure_type,
                    error_message=error_str,
                )

                agent = self.registry.get(agent_id)
                if agent is None:
                    attempt_record.error_message = f"Agent {agent_id} not found"
                    result.attempts.append(attempt_record)
                    break

                retry_start = time.monotonic()
                try:
                    response = agent.process(message)
                    attempt_record.duration_ms = (time.monotonic() - retry_start) * 1000
                    if response is not None:
                        attempt_record.success = True
                        result.attempts.append(attempt_record)
                        result.recovered = True
                        result.response = response
                        result.final_action = RecoveryAction.RETRY
                        result.total_duration_ms = (time.monotonic() - start) * 1000
                        self._history.append(result)
                        return result
                except Exception as e:
                    attempt_record.duration_ms = (time.monotonic() - retry_start) * 1000
                    attempt_record.error_message = str(e)
                    error_str = str(e)

                result.attempts.append(attempt_record)

        # Phase 2: Reflection loop
        reflections: list[str] = []
        for reflect_attempt in range(min(ReflectionEngine.MAX_LAYERS, 2)):
            reflection_prompt = self.reflection_engine.generate_reflection_prompt(
                original_task=message.payload.get("task", ""),
                error_message=error_str,
                attempt_number=reflect_attempt + 1,
                previous_reflections=reflections,
            )

            attempt_record = RecoveryAttempt(
                action=RecoveryAction.REFLECT,
                attempt_number=reflect_attempt + 1,
                agent_id=agent_id,
                failure_type=failure_type,
                error_message=error_str,
                reflection=reflection_prompt[:200],
            )

            agent = self.registry.get(agent_id)
            if agent is None:
                result.attempts.append(attempt_record)
                break

            reflect_msg = Message(
                sender="recovery_manager",
                recipient=agent_id,
                type=MessageType.TASK_REQUEST,
                payload={
                    "task": message.payload.get("task", ""),
                    "context": reflection_prompt,
                    "is_reflection": True,
                },
                correlation_id=message.correlation_id,
            )

            retry_start = time.monotonic()
            try:
                response = agent.process(reflect_msg)
                attempt_record.duration_ms = (time.monotonic() - retry_start) * 1000
                if response is not None:
                    attempt_record.success = True
                    reflections.append(f"Recovered via reflection layer {reflect_attempt + 1}")
                    result.attempts.append(attempt_record)
                    result.recovered = True
                    result.response = response
                    result.final_action = RecoveryAction.REFLECT
                    result.total_duration_ms = (time.monotonic() - start) * 1000
                    self._history.append(result)
                    return result
            except Exception as e:
                attempt_record.duration_ms = (time.monotonic() - retry_start) * 1000
                attempt_record.error_message = str(e)
                error_str = str(e)
                reflections.append(f"Layer {reflect_attempt + 1} failed: {e}")

            result.attempts.append(attempt_record)

        # Phase 3: Escalate
        escalation = RecoveryAttempt(
            action=RecoveryAction.ESCALATE,
            attempt_number=len(result.attempts) + 1,
            agent_id=agent_id,
            failure_type=failure_type,
            error_message=f"All recovery attempts exhausted: {error_str}",
        )
        result.attempts.append(escalation)
        result.final_action = RecoveryAction.ESCALATE
        result.total_duration_ms = (time.monotonic() - start) * 1000

        logger.error(
            "Recovery failed for %s after %d attempts — escalating",
            agent_id,
            len(result.attempts),
        )
        self._history.append(result)
        return result

    def summary(self) -> dict[str, Any]:
        """Summary of all recovery attempts."""
        if not self._history:
            return {"total_recoveries": 0, "success_rate": 0.0}
        return {
            "total_recoveries": len(self._history),
            "success_rate": sum(1 for r in self._history if r.recovered) / len(self._history),
            "by_action": {
                action.value: sum(
                    1 for r in self._history if r.final_action == action
                )
                for action in RecoveryAction
            },
            "avg_attempts": sum(len(r.attempts) for r in self._history) / len(self._history),
        }
