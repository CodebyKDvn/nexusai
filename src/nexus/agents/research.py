"""Research Agent — searches documentation, GitHub, and external knowledge."""

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


class ResearchAgent(Agent):
    """Searches documentation, APIs, and external sources for knowledge."""

    def __init__(
        self,
        agent_id: AgentId,
        bus: MessageBus,
        llm: LLMProvider | None = None,
        memory: MemoryManager | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        super().__init__(agent_id, AgentRole.RESEARCH, bus, memory)
        self.llm = llm
        self.tools = tools

    @property
    def _has_gitnexus(self) -> bool:
        return bool(self.tools and self.tools.get("gitnexus_query"))

    @property
    def system_prompt(self) -> str:
        gitnexus_section = ""
        if self._has_gitnexus:
            gitnexus_section = """

GitNexus Code Intelligence (PREFERRED for code analysis):
Use these tools FIRST before falling back to grep — they query a knowledge graph
instead of reading entire files, saving tokens significantly.

- gitnexus_query: Search by concept (e.g. "auth validation", "database models")
- gitnexus_context: Get 360° view of a symbol (callers, callees, execution flows)
- gitnexus_impact: Blast radius analysis before editing a symbol
- gitnexus_detect_changes: Map git diffs to affected symbols/processes
- gitnexus_analyze: Index a repo (run first if repo not yet indexed)
- gitnexus_status: Check index freshness

Strategy: gitnexus_query first → gitnexus_context for details → grep only for exact text."""

        tool_list = "grep | browser | api_call"
        if self._has_gitnexus:
            tool_list += " | gitnexus_query | gitnexus_context | gitnexus_impact"

        return f"""You are the Research Agent. Your job is to find information needed by the team.

Capabilities:
1. Search code with grep
2. Browse documentation and websites
3. Make API calls to fetch data
4. Analyze and summarize findings
{gitnexus_section}

Respond with:
{{
    "action": "search" | "browse" | "summarize" | "complete",
    "tool": "{tool_list}",
    "params": {{}},
    "findings": "summary of what was found",
    "sources": ["source URLs or file paths"],
    "recommendations": ["actionable recommendations"]
}}"""

    def process(self, message: Message) -> Message | None:
        if message.type != MessageType.TASK_REQUEST:
            return None

        task = message.payload.get("task", "")

        result = self._research_with_llm(task) if self.llm else self._research_stub(task)

        if self.memory and result.get("findings"):
            self.memory.remember(
                f"Research: {result['findings'][:300]}",
                category="research",
                persist=True,
                collection="decisions",
                metadata={"sources": result.get("sources", [])},
            )

        return message.reply(
            MessageType.TASK_RESULT,
            {"status": "complete", "result": result},
        )

    def _research_with_llm(self, task: str) -> dict[str, Any]:
        from nexus.llm.provider import LLMMessage

        assert self.llm is not None

        context = ""
        if self.memory:
            context = self.memory.build_context(task)

        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(
                role="user",
                content=f"Research: {task}\n\nExisting knowledge:\n{context}",
            ),
        ]

        for _ in range(5):
            response = self.llm.chat(messages)
            decision = self.parse_json(response.content)
            if decision is None:
                return {"findings": response.content, "sources": []}

            action = decision.get("action", "complete")
            if action in ("search", "browse") and self.tools:
                tool = self.tools.get(decision.get("tool", ""))
                if tool:
                    tool_result = tool.execute(**decision.get("params", {}))
                    messages.append(LLMMessage(role="assistant", content=response.content))
                    messages.append(
                        LLMMessage(
                            role="user",
                            content=f"Result:\n{json.dumps(tool_result.to_dict())}",
                        )
                    )
                    continue

            return decision

        return {"findings": "Research inconclusive after max iterations", "sources": []}

    def _research_stub(self, task: str) -> dict[str, Any]:
        results: dict[str, Any] = {
            "findings": f"Research topic: {task}",
            "sources": [],
            "recommendations": [],
        }

        if not self.tools:
            return results

        # Prefer GitNexus knowledge graph over raw grep
        gitnexus_query = self.tools.get("gitnexus_query")
        if gitnexus_query:
            search_result = gitnexus_query.execute(query=task)
            if search_result.ok and search_result.output:
                results["sources"].append("gitnexus:knowledge_graph")
                results["findings"] += f"\nGitNexus results:\n{search_result.output[:500]}"
                return results

        # Fallback to grep
        grep = self.tools.get("grep")
        if grep:
            keywords = task.split()[:3]
            for kw in keywords:
                if len(kw) > 3:
                    search_result = grep.execute(pattern=kw)
                    if search_result.ok and search_result.output != "No matches found.":
                        results["sources"].append(f"grep:{kw}")
                        results["findings"] += f"\nFound matches for '{kw}'"

        return results
