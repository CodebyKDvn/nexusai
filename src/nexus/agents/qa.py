"""QA/Test Agent — writes and runs tests, validates correctness."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from nexus.core.agent import Agent, AgentId, AgentRole
from nexus.core.message import Message, MessageBus, MessageType

if TYPE_CHECKING:
    from nexus.core.tool import ToolRegistry
    from nexus.llm.provider import LLMProvider
    from nexus.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class QAAgent(Agent):
    """Writes tests, runs them, validates that code meets requirements."""

    def __init__(
        self,
        agent_id: AgentId,
        bus: MessageBus,
        llm: LLMProvider | None = None,
        memory: MemoryManager | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        super().__init__(agent_id, AgentRole.QA, bus, memory)
        self.llm = llm
        self.tools = tools

    @property
    def system_prompt(self) -> str:
        return """You are the QA Agent. Your job is to ensure code quality through testing.

Responsibilities:
1. Write comprehensive tests for new code
2. Run existing test suites
3. Validate that implementations meet requirements
4. Report test results with pass/fail details

Respond with:
{
    "action": "write_tests" | "run_tests" | "complete",
    "tests": [
        {"path": "test file path", "content": "test code"}
    ],
    "command": "test command to run",
    "results": {
        "passed": 0,
        "failed": 0,
        "errors": [],
        "summary": "test summary"
    }
}"""

    def process(self, message: Message) -> Message | None:
        if message.type != MessageType.TASK_REQUEST:
            return None

        task = message.payload.get("task", "")
        content = message.payload.get("content", "")

        result = self._qa_with_llm(task, content) if self.llm else self._qa_stub(task)

        if self.memory:
            self.memory.remember(
                f"QA result: {json.dumps(result.get('results', {}))[:200]}",
                category="qa",
            )

        return message.reply(
            MessageType.TASK_RESULT,
            {"status": "complete", "result": result},
        )

    def _qa_with_llm(self, task: str, content: str) -> dict[str, Any]:
        from nexus.llm.provider import LLMMessage

        assert self.llm is not None
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(
                role="user",
                content=f"Task: {task}\n\nCode to test:\n{content}",
            ),
        ]

        for _ in range(3):
            response = self.llm.chat(messages)
            decision = self.parse_json(response.content)
            if decision is None:
                return {"results": {"summary": response.content}}

            if decision.get("action") == "write_tests" and self.tools:
                for test in decision.get("tests", []):
                    write_tool = self.tools.get("file_write")
                    if write_tool:
                        write_tool.execute(path=test["path"], content=test["content"])
                messages.append(LLMMessage(role="assistant", content=response.content))
                messages.append(
                    LLMMessage(role="user", content="Tests written. Now run them.")
                )
                continue

            if decision.get("action") == "run_tests" and self.tools:
                terminal = self.tools.get("terminal")
                if terminal:
                    cmd = decision.get("command", "pytest")
                    result = terminal.execute(command=cmd)
                    decision["results"] = {
                        "output": result.output,
                        "passed": result.ok,
                        "summary": f"Tests {'passed' if result.ok else 'failed'}",
                    }

            return decision

        return {"results": {"summary": "Max QA iterations reached"}}

    def _qa_stub(self, task: str) -> dict[str, Any]:
        return {
            "results": {
                "summary": f"QA review needed for: {task}",
                "note": "LLM provider not configured",
            }
        }
