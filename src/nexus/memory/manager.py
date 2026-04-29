"""Memory manager — unified interface for short-term and long-term memory with RAG."""

from __future__ import annotations

import logging
from typing import Any

from nexus.memory.long_term import LongTermMemory, RetrievedMemory
from nexus.memory.short_term import ShortTermMemory

logger = logging.getLogger(__name__)


class MemoryManager:
    """Unified memory interface combining short-term and long-term storage."""

    def __init__(
        self,
        persist_dir: str = ".nexus/memory",
        short_term_capacity: int = 50,
    ) -> None:
        self.short_term = ShortTermMemory(capacity=short_term_capacity)
        self.long_term = LongTermMemory(persist_dir=persist_dir)

    def remember(
        self,
        content: str,
        *,
        category: str = "general",
        persist: bool = False,
        collection: str = "reflections",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Store a memory. Always goes to short-term; optionally persists to long-term."""
        self.short_term.add(content, category=category)

        if persist:
            doc_id = self.long_term.store(
                collection=collection,
                content=content,
                metadata=metadata or {"category": category},
            )
            return doc_id
        return None

    def recall(
        self,
        query: str,
        *,
        n_results: int = 5,
        collections: list[str] | None = None,
        include_short_term: bool = True,
    ) -> list[RetrievedMemory]:
        """Retrieve relevant memories using RAG."""
        results: list[RetrievedMemory] = []

        if include_short_term:
            short_term_matches = self.short_term.search(query)
            for entry in short_term_matches[:n_results]:
                results.append(
                    RetrievedMemory(
                        content=entry.content,
                        metadata={"source": "short_term", "category": entry.category},
                        distance=0.0,
                        id="short_term",
                    )
                )

        target_collections = collections or LongTermMemory.COLLECTIONS
        for collection in target_collections:
            long_term_results = self.long_term.retrieve(
                collection=collection,
                query=query,
                n_results=n_results,
            )
            results.extend(long_term_results)

        results.sort(key=lambda m: m.distance)
        return results[:n_results]

    def build_context(self, query: str, max_tokens: int = 2000) -> str:
        """Build a context string from relevant memories for RAG injection."""
        memories = self.recall(query, n_results=10)

        if not memories:
            recent = self.short_term.get_context_string(n=5)
            return f"Recent context:\n{recent}" if recent else ""

        parts = ["Relevant knowledge from memory:"]
        char_count = 0
        approx_token_limit = max_tokens * 4

        for mem in memories:
            entry = f"- [{mem.metadata.get('category', 'unknown')}] {mem.content}"
            if char_count + len(entry) > approx_token_limit:
                break
            parts.append(entry)
            char_count += len(entry)

        return "\n".join(parts)

    def store_reflection(
        self,
        reflection: str,
        *,
        task: str = "",
        score: float = 0.0,
    ) -> str:
        """Store a reflection from the critic agent."""
        return self.long_term.store(
            collection="reflections",
            content=reflection,
            metadata={"task": task, "score": score},
        )

    def store_code_pattern(
        self,
        pattern: str,
        *,
        language: str = "",
        context: str = "",
    ) -> str:
        """Store a reusable code pattern."""
        return self.long_term.store(
            collection="code_patterns",
            content=pattern,
            metadata={"language": language, "context": context},
        )

    def store_decision(self, decision: str, *, rationale: str = "") -> str:
        """Store an architecture/design decision."""
        return self.long_term.store(
            collection="decisions",
            content=decision,
            metadata={"rationale": rationale},
        )

    def store_bug(self, bug: str, *, fix: str = "", severity: str = "medium") -> str:
        """Store a bug and its fix for future reference."""
        return self.long_term.store(
            collection="bugs",
            content=f"Bug: {bug}\nFix: {fix}",
            metadata={"severity": severity},
        )

    def clear_short_term(self) -> None:
        """Clear short-term memory between tasks."""
        self.short_term.clear()
