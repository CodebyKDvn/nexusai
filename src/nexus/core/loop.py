"""Agent execution loop — the core reasoning cycle."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from nexus.core.message import Message, MessageType

if TYPE_CHECKING:
    from nexus.core.agent import Agent
    from nexus.core.registry import AgentRegistry

logger = logging.getLogger(__name__)


@dataclass
class LoopState:
    iteration: int = 0
    max_iterations: int = 20
    completed: bool = False
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class AgentLoop:
    """Drives the understand → plan → act → observe → reflect cycle."""

    def __init__(self, registry: AgentRegistry, max_iterations: int = 20) -> None:
        self.registry = registry
        self.max_iterations = max_iterations
        self._state = LoopState(max_iterations=max_iterations)

    @property
    def state(self) -> LoopState:
        return self._state

    def run(self, initial_message: Message) -> LoopState:
        """Run the agent loop starting from an initial message."""
        self._state = LoopState(max_iterations=self.max_iterations)

        target = self.registry.get(initial_message.recipient)
        if not target:
            self._state.errors.append(
                f"No agent found for recipient: {initial_message.recipient}"
            )
            self._state.completed = True
            return self._state

        pending: list[tuple[Agent, Message]] = [(target, initial_message)]

        while pending and self._state.iteration < self.max_iterations:
            self._state.iteration += 1
            next_pending: list[tuple[Agent, Message]] = []

            for agent, message in pending:
                logger.info(
                    "Loop iteration %d: %s processing %s",
                    self._state.iteration,
                    agent.agent_id,
                    message.type.value,
                )
                try:
                    response = agent.process(message)
                except Exception as e:
                    logger.exception("Agent %s raised an error", agent.agent_id)
                    self._state.errors.append(f"{agent.agent_id}: {e}")
                    continue

                if response is None:
                    continue

                self._state.results.append(response.to_dict())

                if response.type == MessageType.TASK_RESULT:
                    payload = response.payload
                    if payload.get("status") == "complete":
                        self._state.completed = True
                        return self._state

                next_agent = self.registry.get(response.recipient)
                if next_agent:
                    next_pending.append((next_agent, response))

            pending = next_pending

        if not self._state.completed:
            self._state.errors.append(
                f"Loop ended after {self._state.iteration} iterations without completion"
            )

        return self._state
