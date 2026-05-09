"""Debugger Agent — detects and fixes errors using logs and execution outputs."""

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


class DebuggerAgent(Agent):
    """Investigates errors, analyzes logs, proposes and applies fixes."""

    def __init__(
        self,
        agent_id: AgentId,
        bus: MessageBus,
        llm: LLMProvider | None = None,
        memory: MemoryManager | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        super().__init__(agent_id, AgentRole.DEBUGGER, bus, memory)
        self.llm = llm
        self.tools = tools

    @property
    def system_prompt(self) -> str:
        return """You are the Debugger Agent. Your job is to find and fix bugs.

Process:
1. Analyze the error message and stack trace
2. Use tools to read relevant source files
3. Identify root cause
4. Propose a fix
5. Apply the fix and verify

Respond with:
{
    "action": "investigate" | "fix" | "complete",
    "tool": "tool_name (for investigate)",
    "params": {},
    "diagnosis": "root cause analysis",
    "fix": {
        "file": "path",
        "old_code": "original code",
        "new_code": "fixed code"
    },
    "summary": "what was fixed and why"
}"""

    def process(self, message: Message) -> Message | None:
        if message.type != MessageType.TASK_REQUEST:
            return None

        task = message.payload.get("task", "")
        error_details = message.payload.get("error_details", {})

        if self.memory:
            past_bugs = self.memory.recall(task, collections=["bugs"], n_results=3)
            context = ""
            if past_bugs:
                context = "Similar past bugs:\n"
                for bug in past_bugs:
                    context += f"- {bug.content[:200]}\n"
        else:
            context = ""

        result = (
            self._debug_with_llm(task, error_details, context)
            if self.llm
            else self._debug_stub(task, error_details)
        )

        if self.memory and result.get("diagnosis"):
            self.memory.store_bug(
                bug=result.get("diagnosis", ""),
                fix=result.get("summary", ""),
            )

        return message.reply(
            MessageType.TASK_RESULT,
            {"status": "complete", "result": result},
        )

    def _debug_with_llm(
        self, task: str, error_details: dict[str, Any], context: str
    ) -> dict[str, Any]:
        from nexus.llm.provider import LLMMessage

        assert self.llm is not None
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(
                role="user",
                content=(
                    f"Debug this issue: {task}\n\n"
                    f"Error details: {json.dumps(error_details)}\n\n"
                    f"Context: {context}"
                ),
            ),
        ]

        for _ in range(5):
            response = self.llm.chat(messages)
            decision = self.parse_json(response.content)
            if decision is None:
                return {"diagnosis": response.content, "summary": response.content}

            if decision.get("action") == "investigate" and self.tools:
                tool = self.tools.get(decision.get("tool", ""))
                if tool:
                    tool_result = tool.execute(**decision.get("params", {}))
                    messages.append(LLMMessage(role="assistant", content=response.content))
                    messages.append(
                        LLMMessage(
                            role="user",
                            content=f"Tool result:\n{json.dumps(tool_result.to_dict())}",
                        )
                    )
                    continue

            if decision.get("action") == "fix" and self.tools:
                fix = decision.get("fix", {})
                if fix:
                    edit_tool = self.tools.get("file_edit")
                    if edit_tool:
                        edit_tool.execute(
                            path=fix["file"],
                            old_string=fix["old_code"],
                            new_string=fix["new_code"],
                        )

            return decision

        return {"diagnosis": "Could not diagnose within iteration limit", "summary": ""}

    def _debug_stub(self, task: str, error_details: dict[str, Any]) -> dict[str, Any]:
        return {
            "diagnosis": f"Analysis needed for: {task}",
            "error_details": error_details,
            "summary": "LLM provider not configured — manual debugging required",
        }
