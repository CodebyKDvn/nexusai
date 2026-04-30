"""Frontend Developer Agent — builds UIs, layouts, client-side logic."""

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


class FrontendDeveloperAgent(Agent):
    """Specializes in frontend development: UI components, styling, client-side logic."""

    def __init__(
        self,
        agent_id: AgentId,
        bus: MessageBus,
        llm: LLMProvider | None = None,
        memory: MemoryManager | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        super().__init__(agent_id, AgentRole.FRONTEND_DEVELOPER, bus, memory)
        self.llm = llm
        self.tools = tools

    @property
    def system_prompt(self) -> str:
        tool_docs = ""
        if self.tools:
            for tool in self.tools.list_tools():
                params = ", ".join(p.name for p in tool.parameters)
                tool_docs += f"- {tool.name}({params}): {tool.description}\n"

        return f"""You are the Frontend Developer Agent.

Your expertise:
1. HTML, CSS, JavaScript/TypeScript
2. React, Vue, Angular, and other frontend frameworks
3. Responsive design, accessibility, and performance optimization
4. UI component architecture and design systems
5. Client-side state management and API integration

Design principles:
- Apple-inspired minimalism and clarity
- OpenAI-style clean, structured layouts
- Tesla-inspired futuristic simplicity
- Consistent typography, spacing, and visual hierarchy

Available tools:
{tool_docs}

When you need to use a tool, respond with:
{{
    "action": "use_tool",
    "tool": "tool_name",
    "params": {{...}},
    "reasoning": "why this tool is needed"
}}

When you have a solution ready:
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
                context += "\n\nRelevant UI patterns:\n"
                for p in patterns:
                    context += f"- {p.content[:200]}\n"

        result = (
            self._develop_with_llm(task, context) if self.llm else self._develop_stub(task)
        )

        if self.memory:
            summary = result.get("summary", task[:100])
            self.memory.remember(
                f"Frontend: {summary}",
                category="development",
                persist=True,
                collection="code_patterns",
                metadata={"task": task[:200], "domain": "frontend"},
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
                content=f"Implement the following frontend task:\n\n{task}\n\nContext:\n{context}",
            ),
        ]

        max_iterations = 5
        for _iteration in range(max_iterations):
            response = self.llm.chat(messages)

            decision = self.parse_json(response.content)
            if decision is None:
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
            "summary": f"Frontend implementation plan for: {task}",
            "files": [],
            "note": "LLM provider not configured — returning stub response",
            "suggestions": [
                "Create component structure with React/Vue",
                "Add responsive CSS with a design system",
                "Implement client-side state management",
                "Wire up API calls for data fetching",
            ],
        }
