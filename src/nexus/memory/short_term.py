"""Short-term memory — in-process context window."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class MemoryEntry:
    content: str
    category: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class ShortTermMemory:
    """Bounded context window for current task state."""

    def __init__(self, capacity: int = 50) -> None:
        self._entries: deque[MemoryEntry] = deque(maxlen=capacity)
        self._capacity = capacity

    def add(self, content: str, category: str = "general", **metadata: Any) -> None:
        self._entries.append(
            MemoryEntry(content=content, category=category, metadata=metadata)
        )

    def get_recent(self, n: int = 10, category: str | None = None) -> list[MemoryEntry]:
        entries = list(self._entries)
        if category:
            entries = [e for e in entries if e.category == category]
        return entries[-n:]

    def get_context_string(self, n: int = 10) -> str:
        entries = self.get_recent(n)
        if not entries:
            return ""
        parts = []
        for entry in entries:
            parts.append(f"[{entry.category}] {entry.content}")
        return "\n".join(parts)

    def search(self, keyword: str) -> list[MemoryEntry]:
        keyword_lower = keyword.lower()
        return [e for e in self._entries if keyword_lower in e.content.lower()]

    def clear(self) -> None:
        self._entries.clear()

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def capacity(self) -> int:
        return self._capacity
