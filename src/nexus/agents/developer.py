"""Developer Agent — writes code, designs APIs, implements features."""

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


class DeveloperAgent(Agent):
    """Implements features, writes code, designs systems."""

    def __init__(
        self,
        agent_id: AgentId,
        bus: MessageBus,
        llm: LLMProvider | None = None,
        memory: MemoryManager | None = None,
        tools: ToolRegistry | None = None,
        specialty: str = "fullstack",
    ) -> None:
        super().__init__(agent_id, AgentRole.DEVELOPER, bus, memory)
        self.llm = llm
        self.tools = tools
        self.specialty = specialty

    @property
    def system_prompt(self) -> str:
        tool_docs = ""
        if self.tools:
            for tool in self.tools.list_tools():
                params = ", ".join(p.name for p in tool.parameters)
                tool_docs += f"- {tool.name}({params}): {tool.description}\n"

        return f"""You are a Developer Agent specializing in {self.specialty} development.

Your responsibilities:
1. Write clean, well-structured, production-quality code
2. Follow existing project conventions
3. Use available tools to read/write files and run commands
4. Always verify your changes compile/run correctly

Available tools:
{tool_docs}

When you need to use a tool, respond with:
{{
    "action": "use_tool",
    "tool": "tool_name",
    "params": {{...}},
    "reasoning": "why this tool is needed"
}}

When you have a code solution ready:
{{
    "action": "complete",
    "files": [
        {{"path": "path/to/file", "content": "file content"}}
    ],
    "summary": "what was implemented"
}}"""

    def process(self, message: Message) -> Message | None:
        if message.type != MessageType.TASK_REQUEST:
            return None

        task = message.payload.get("task", "")
        context = message.payload.get("context", "")

        if self.memory:
            patterns = self.memory.recall(
                task, collections=["code_patterns"], n_results=3
            )
            if patterns:
                context += "\n\nRelevant code patterns:\n"
                for p in patterns:
                    context += f"- {p.content[:200]}\n"

        result = self._develop_with_llm(task, context) if self.llm else self._develop_stub(task)

        if self.memory:
            summary = result.get("summary", task[:100])
            self.memory.remember(
                f"Developed: {summary}",
                category="development",
                persist=True,
                collection="code_patterns",
                metadata={"task": task[:200]},
            )

        return message.reply(
            MessageType.TASK_RESULT,
            {"status": "needs_review", "result": result},
        )

    def _develop_with_llm(self, task: str, context: str) -> dict[str, Any]:
        from nexus.llm.provider import LLMMessage

        assert self.llm is not None
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(
                role="user",
                content=f"Implement the following:\n\n{task}\n\nContext:\n{context}",
            ),
        ]

        max_iterations = 5
        for _iteration in range(max_iterations):
            response = self.llm.chat(messages)

            try:
                decision: dict[str, Any] = json.loads(response.content)
            except json.JSONDecodeError:
                return {"action": "complete", "summary": response.content, "files": []}

            if decision.get("action") == "use_tool" and self.tools:
                tool_name = decision.get("tool", "")
                tool_params = decision.get("params", {})
                tool = self.tools.get(tool_name)

                if tool:
                    tool_result = tool.execute(**tool_params)
                    messages.append(LLMMessage(role="assistant", content=response.content))
                    messages.append(
                        LLMMessage(
                            role="user",
                            content=f"Tool result:\n{json.dumps(tool_result.to_dict())}",
                        )
                    )
                    continue

            if decision.get("action") == "complete":
                files = decision.get("files", [])
                if self.tools and files:
                    for f in files:
                        write_tool = self.tools.get("file_write")
                        if write_tool:
                            write_tool.execute(path=f["path"], content=f["content"])
                return decision

        return {"action": "complete", "summary": "Max iterations reached", "files": []}

    def _develop_stub(self, task: str) -> dict[str, Any]:
        return {
            "action": "complete",
            "summary": f"Implementation plan for: {task}",
            "files": [],
            "note": "LLM provider not configured — returning stub response",
        }
