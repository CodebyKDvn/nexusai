"""Memory Agent — manages knowledge storage and retrieval."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nexus.core.agent import Agent, AgentId, AgentRole
from nexus.core.message import Message, MessageBus, MessageType

if TYPE_CHECKING:
    from nexus.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class MemoryAgentImpl(Agent):
    """Manages persistent memory: stores patterns, retrieves knowledge, maintains context."""

    def __init__(
        self,
        agent_id: AgentId,
        bus: MessageBus,
        memory: MemoryManager | None = None,
    ) -> None:
        super().__init__(agent_id, AgentRole.MEMORY, bus, memory)

    def process(self, message: Message) -> Message | None:
        if message.type == MessageType.QUERY:
            return self._handle_query(message)
        elif message.type == MessageType.TASK_REQUEST:
            return self._handle_store_request(message)
        return None

    def _handle_query(self, message: Message) -> Message | None:
        query = message.payload.get("query", "")
        collections = message.payload.get("collections")
        n_results = message.payload.get("n_results", 5)

        if not self.memory:
            return message.reply(
                MessageType.TASK_RESULT,
                {"status": "complete", "result": {"memories": [], "context": ""}},
            )

        memories = self.memory.recall(
            query, n_results=n_results, collections=collections
        )
        context = self.memory.build_context(query)

        result = {
            "memories": [
                {"content": m.content, "metadata": m.metadata, "distance": m.distance}
                for m in memories
            ],
            "context": context,
        }

        return message.reply(
            MessageType.TASK_RESULT,
            {"status": "complete", "result": result},
        )

    def _handle_store_request(self, message: Message) -> Message | None:
        content = message.payload.get("content", "")
        collection = message.payload.get("collection", "reflections")
        metadata = message.payload.get("metadata", {})
        category = message.payload.get("category", "general")

        if not self.memory:
            return message.reply(
                MessageType.ERROR,
                {"error": "Memory manager not configured"},
            )

        doc_id = self.memory.remember(
            content,
            category=category,
            persist=True,
            collection=collection,
            metadata=metadata,
        )

        return message.reply(
            MessageType.TASK_RESULT,
            {"status": "complete", "result": {"stored_id": doc_id}},
        )
