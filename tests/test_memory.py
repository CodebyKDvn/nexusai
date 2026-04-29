"""Tests for the memory system."""

from __future__ import annotations

from nexus.memory.long_term import LongTermMemory
from nexus.memory.manager import MemoryManager
from nexus.memory.short_term import ShortTermMemory


class TestShortTermMemory:
    def test_add_and_retrieve(self) -> None:
        mem = ShortTermMemory(capacity=10)
        mem.add("First entry", category="test")
        mem.add("Second entry", category="test")

        recent = mem.get_recent(5)
        assert len(recent) == 2
        assert recent[0].content == "First entry"
        assert recent[1].content == "Second entry"

    def test_capacity_limit(self) -> None:
        mem = ShortTermMemory(capacity=3)
        for i in range(5):
            mem.add(f"Entry {i}")

        assert mem.size == 3
        recent = mem.get_recent(10)
        assert recent[0].content == "Entry 2"

    def test_category_filter(self) -> None:
        mem = ShortTermMemory(capacity=10)
        mem.add("Code entry", category="code")
        mem.add("Bug entry", category="bug")
        mem.add("Another code", category="code")

        code_entries = mem.get_recent(10, category="code")
        assert len(code_entries) == 2

    def test_search(self) -> None:
        mem = ShortTermMemory(capacity=10)
        mem.add("Python function for sorting")
        mem.add("JavaScript array method")
        mem.add("Python class definition")

        results = mem.search("Python")
        assert len(results) == 2

        results = mem.search("nonexistent")
        assert len(results) == 0

    def test_clear(self) -> None:
        mem = ShortTermMemory(capacity=10)
        mem.add("entry")
        assert mem.size == 1

        mem.clear()
        assert mem.size == 0

    def test_context_string(self) -> None:
        mem = ShortTermMemory(capacity=10)
        mem.add("First thing", category="task")
        mem.add("Second thing", category="result")

        context = mem.get_context_string(5)
        assert "task" in context
        assert "First thing" in context
        assert "result" in context


class TestLongTermMemory:
    def test_store_and_retrieve_fallback(self) -> None:
        mem = LongTermMemory(persist_dir="/tmp/test_nexus_mem")
        doc_id = mem.store(
            "code_patterns",
            "Use list comprehensions for filtering",
            metadata={"language": "python"},
        )
        assert doc_id

        results = mem.retrieve("code_patterns", "list comprehension")
        assert len(results) >= 1
        assert "list comprehension" in results[0].content.lower()

    def test_store_multiple_collections(self) -> None:
        mem = LongTermMemory(persist_dir="/tmp/test_nexus_mem2")

        mem.store("code_patterns", "Use dataclasses for DTOs")
        mem.store("bugs", "Off-by-one error in loop")
        mem.store("decisions", "Use PostgreSQL for persistence")

        patterns = mem.retrieve("code_patterns", "dataclass")
        assert len(patterns) >= 1

    def test_list_collection(self) -> None:
        mem = LongTermMemory(persist_dir="/tmp/test_nexus_mem3")
        mem.store("reflections", "Always validate user input")
        mem.store("reflections", "Handle edge cases explicitly")

        items = mem.list_collection("reflections")
        assert len(items) >= 2


class TestMemoryManager:
    def test_remember_short_term(self) -> None:
        mgr = MemoryManager(persist_dir="/tmp/test_nexus_mgr")
        result = mgr.remember("Short term only", category="test")
        assert result is None
        assert mgr.short_term.size == 1

    def test_remember_persistent(self) -> None:
        mgr = MemoryManager(persist_dir="/tmp/test_nexus_mgr2")
        doc_id = mgr.remember(
            "Persist this pattern",
            category="code",
            persist=True,
            collection="code_patterns",
        )
        assert doc_id is not None

    def test_recall(self) -> None:
        mgr = MemoryManager(persist_dir="/tmp/test_nexus_mgr3")
        mgr.remember("Python list comprehension pattern", category="code")

        results = mgr.recall("list comprehension", include_short_term=True)
        assert len(results) >= 1

    def test_build_context(self) -> None:
        mgr = MemoryManager(persist_dir="/tmp/test_nexus_mgr4")
        mgr.remember("Use async/await for I/O bound operations", category="pattern")

        context = mgr.build_context("async operations")
        assert isinstance(context, str)

    def test_store_reflection(self) -> None:
        mgr = MemoryManager(persist_dir="/tmp/test_nexus_mgr5")
        doc_id = mgr.store_reflection(
            "Always check return values",
            task="implement error handling",
            score=8.0,
        )
        assert doc_id

    def test_store_bug(self) -> None:
        mgr = MemoryManager(persist_dir="/tmp/test_nexus_mgr6")
        doc_id = mgr.store_bug(
            "Null pointer in user handler",
            fix="Added null check before access",
            severity="high",
        )
        assert doc_id

    def test_clear_short_term(self) -> None:
        mgr = MemoryManager(persist_dir="/tmp/test_nexus_mgr7")
        mgr.remember("Entry 1")
        mgr.remember("Entry 2")
        assert mgr.short_term.size == 2

        mgr.clear_short_term()
        assert mgr.short_term.size == 0
