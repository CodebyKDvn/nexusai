"""Base Agent class — all agents inherit from this."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from nexus.core.message import BROADCAST, Message, MessageBus, MessageType

if TYPE_CHECKING:
    from nexus.memory.manager import MemoryManager

logger = logging.getLogger(__name__)

AgentId = str


class AgentRole(StrEnum):
    ORCHESTRATOR = "orchestrator"
    PLANNER = "planner"
    LEAD_DEVELOPER = "lead_developer"
    DEVELOPER = "developer"
    FRONTEND_DEVELOPER = "frontend_developer"
    BACKEND_DEVELOPER = "backend_developer"
    UX_UI_DESIGNER = "ux_ui_designer"
    DEBUGGER = "debugger"
    QA = "qa"
    RESEARCH = "research"
    MEMORY = "memory"
    CRITIC = "critic"
    TOOL_EXECUTOR = "tool_executor"


class Agent(ABC):
    """Base class for all Nexus agents."""

    def __init__(
        self,
        agent_id: AgentId,
        role: AgentRole,
        bus: MessageBus,
        memory: MemoryManager | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.role = role
        self.bus = bus
        self.memory = memory
        self._inbox: list[Message] = []
        self._context: dict[str, Any] = {}
        self._iteration_count = 0

        self.bus.subscribe(self.agent_id, self._receive)

    @property
    def system_prompt(self) -> str:
        """System prompt defining this agent's behavior."""
        return f"You are the {self.role.value} agent in an AI development team."

    def _receive(self, message: Message) -> None:
        logger.debug(
            "Agent %s received message %s from %s",
            self.agent_id,
            message.type.value,
            message.sender,
        )
        self._inbox.append(message)

    def send(
        self,
        recipient: str,
        type: MessageType,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> Message:
        msg = Message(
            sender=self.agent_id,
            recipient=recipient,
            type=type,
            payload=payload,
            correlation_id=correlation_id,
        )
        self.bus.publish(msg)
        return msg

    def broadcast(self, type: MessageType, payload: dict[str, Any]) -> Message:
        return self.send(BROADCAST, type, payload)

    def get_pending_messages(self) -> list[Message]:
        messages = list(self._inbox)
        self._inbox.clear()
        return messages

    @abstractmethod
    def process(self, message: Message) -> Message | None:
        """Process an incoming message and optionally return a response."""

    def update_context(self, key: str, value: Any) -> None:
        self._context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        return self._context.get(key, default)

    def clear_context(self) -> None:
        self._context.clear()
        self._iteration_count = 0

    def parse_json(self, content: str) -> dict[str, Any] | None:
        """Safely parse JSON from LLM response, handling markdown code blocks."""
        content = content.strip()
        if content.startswith("```"):
            # Strip code blocks
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        try:
            import json
            return json.loads(content) # type: ignore[no-any-return]
        except json.JSONDecodeError:
            return None

    def __repr__(self) -> str:
        return f"Agent({self.agent_id}, role={self.role.value})"
