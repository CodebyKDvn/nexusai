"""Message types and message bus for inter-agent communication."""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class MessageType(StrEnum):
    TASK_REQUEST = "task_request"
    TASK_RESULT = "task_result"
    QUERY = "query"
    EVENT = "event"
    ERROR = "error"
    STATUS = "status"
    REFLECTION = "reflection"


@dataclass
class Message:
    sender: str
    recipient: str
    type: MessageType
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str | None = None
    priority: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def reply(self, type: MessageType, payload: dict[str, Any]) -> Message:
        return Message(
            sender=self.recipient,
            recipient=self.sender,
            type=type,
            payload=payload,
            correlation_id=self.correlation_id or self.id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "type": self.type.value,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "priority": self.priority,
            "timestamp": self.timestamp.isoformat(),
        }


BROADCAST = "__broadcast__"

MessageHandler = Callable[[Message], None]


class MessageBus:
    """Pub/sub message bus for agent communication."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[MessageHandler]] = defaultdict(list)
        self._history: list[Message] = []
        self._max_history: int = 1000

    def subscribe(self, channel: str, handler: MessageHandler) -> None:
        self._subscribers[channel].append(handler)

    def unsubscribe(self, channel: str, handler: MessageHandler) -> None:
        if channel in self._subscribers:
            self._subscribers[channel] = [
                h for h in self._subscribers[channel] if h is not handler
            ]

    def publish(self, message: Message) -> None:
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        for handler in self._subscribers.get(message.recipient, []):
            handler(message)

        if message.recipient != BROADCAST:
            for handler in self._subscribers.get(BROADCAST, []):
                handler(message)

    def get_history(
        self,
        *,
        sender: str | None = None,
        recipient: str | None = None,
        type: MessageType | None = None,
        correlation_id: str | None = None,
        limit: int = 50,
    ) -> list[Message]:
        results = self._history
        if sender:
            results = [m for m in results if m.sender == sender]
        if recipient:
            results = [m for m in results if m.recipient == recipient]
        if type:
            results = [m for m in results if m.type == type]
        if correlation_id:
            results = [m for m in results if m.correlation_id == correlation_id]
        return results[-limit:]
