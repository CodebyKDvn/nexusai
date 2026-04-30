"""Orchestrator Agent — receives user requests, clarifies, delegates, maintains state."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from nexus.core.agent import Agent, AgentId, AgentRole
from nexus.core.message import BROADCAST, Message, MessageBus, MessageType

if TYPE_CHECKING:
    from nexus.llm.provider import LLMProvider
    from nexus.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class OrchestratorAgent(Agent):
    """Central coordinator that receives tasks, delegates work, and tracks progress."""

    def __init__(
        self,
        agent_id: AgentId,
        bus: MessageBus,
        llm: LLMProvider | None = None,
        memory: MemoryManager | None = None,
    ) -> None:
        super().__init__(agent_id, AgentRole.ORCHESTRATOR, bus, memory)
        self.llm = llm
        self._task_queue: list[dict[str, Any]] = []
        self._active_tasks: dict[str, dict[str, Any]] = {}
        self._completed_tasks: list[dict[str, Any]] = []

        self.bus.subscribe(BROADCAST, self._on_broadcast)

    def _on_broadcast(self, message: Message) -> None:
        if message.sender != self.agent_id:
            logger.debug("Orchestrator observed broadcast from %s", message.sender)

    @property
    def system_prompt(self) -> str:
        return """You are the Orchestrator Agent — the central coordinator of an AI dev team.

Your responsibilities:
1. Understand user requests and clarify ambiguities
2. Break down complex requests into delegatable tasks
3. Route tasks to the appropriate specialist agent
4. Track progress and ensure all subtasks complete
5. Synthesize results into a coherent response

You delegate to these agents:
- planner: For breaking down complex tasks into structured plans
- ux_ui_designer: For UX/UI design, prototypes, wireframes, visual style, design direction
- frontend_developer: For building UIs, layouts, CSS, client-side logic, React/Vue/Angular
- backend_developer: For building APIs, databases, server-side logic, authentication
- debugger: For finding and fixing bugs
- qa: For writing and running tests
- research: For looking up documentation and external knowledge
- critic: For evaluating output quality

Respond with a JSON object containing:
{
    "action": "delegate" | "respond" | "clarify",
    "target_agent": "agent_id (for delegate)",
    "task": "task description",
    "context": "relevant context",
    "response": "direct response to user (for respond/clarify)"
}"""

    def process(self, message: Message) -> Message | None:
        if message.type == MessageType.TASK_REQUEST:
            return self._handle_task_request(message)
        elif message.type == MessageType.TASK_RESULT:
            return self._handle_task_result(message)
        elif message.type == MessageType.ERROR:
            return self._handle_error(message)
        return None

    def _handle_task_request(self, message: Message) -> Message | None:
        task = message.payload.get("task", "")
        correlation_id = message.correlation_id or message.id

        if self.memory:
            context = self.memory.build_context(task)
            self.memory.remember(
                f"Received task: {task}", category="task", persist=False
            )
        else:
            context = ""

        return (
            self._delegate_with_llm(message, task, context, correlation_id)
            if self.llm
            else self._delegate_rule_based(message, task, correlation_id)
        )

    def _delegate_with_llm(
        self,
        message: Message,
        task: str,
        context: str,
        correlation_id: str,
    ) -> Message | None:
        from nexus.llm.provider import LLMMessage

        assert self.llm is not None
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(
                role="user",
                content=f"Task: {task}\n\nMemory context:\n{context}",
            ),
        ]
        response = self.llm.chat(messages)

        try:
            decision = json.loads(response.content)
        except json.JSONDecodeError:
            decision = {"action": "respond", "response": response.content}

        action = decision.get("action", "respond")

        if action == "delegate":
            target = decision.get("target_agent", "planner")
            return self.send(
                target,
                MessageType.TASK_REQUEST,
                {
                    "task": decision.get("task", task),
                    "context": decision.get("context", context),
                    "original_request": task,
                },
                correlation_id=correlation_id,
            )
        elif action == "clarify":
            return message.reply(
                MessageType.QUERY,
                {"question": decision.get("response", "Could you clarify your request?")},
            )
        else:
            return message.reply(
                MessageType.TASK_RESULT,
                {
                    "status": "complete",
                    "result": decision.get("response", response.content),
                },
            )

    def _delegate_rule_based(
        self, message: Message, task: str, correlation_id: str
    ) -> Message | None:
        task_lower = task.lower()

        if any(
            kw in task_lower
            for kw in [
                "design", "ux", "prototype", "mockup", "wireframe",
                "visual", "brand", "typography", "color scheme",
                "landing page design", "infographic",
            ]
        ):
            target = "ux_ui_designer"
        elif any(kw in task_lower for kw in ["plan", "architect", "break down"]):
            target = "planner"
        elif any(kw in task_lower for kw in ["bug", "fix", "error", "debug"]):
            target = "debugger"
        elif any(kw in task_lower for kw in ["test", "verify", "validate", "qa"]):
            target = "qa"
        elif any(
            kw in task_lower
            for kw in [
                "search", "find", "look up", "research", "docs",
                "analyze codebase", "code intelligence", "knowledge graph",
                "index repo", "blast radius", "impact analysis",
            ]
        ):
            target = "research"
        elif any(kw in task_lower for kw in ["review", "evaluate", "critique", "improve"]):
            target = "critic"
        elif any(
            kw in task_lower
            for kw in [
                "frontend", "ui", "component", "css", "html", "react",
                "vue", "angular", "layout", "style", "responsive",
            ]
        ):
            target = "frontend_developer"
        elif any(
            kw in task_lower
            for kw in [
                "backend", "api", "database", "server", "endpoint",
                "rest", "graphql", "auth", "migration",
            ]
        ):
            target = "backend_developer"
        else:
            target = "planner"

        self._active_tasks[correlation_id] = {
            "task": task,
            "target": target,
            "status": "delegated",
        }

        return self.send(
            target,
            MessageType.TASK_REQUEST,
            {"task": task, "context": "", "original_request": task},
            correlation_id=correlation_id,
        )

    def _handle_task_result(self, message: Message) -> Message | None:
        correlation_id = message.correlation_id
        result = message.payload.get("result", "")
        status = message.payload.get("status", "")

        if correlation_id and correlation_id in self._active_tasks:
            task_info = self._active_tasks.pop(correlation_id)
            task_info["status"] = status
            task_info["result"] = result
            self._completed_tasks.append(task_info)

        if self.memory:
            result_str = str(result)[:200] if result else ""
            self.memory.remember(
                f"Task completed by {message.sender}: {result_str}",
                category="result",
                persist=True,
                collection="reflections",
            )

        if status == "needs_review":
            return self.send(
                "critic",
                MessageType.TASK_REQUEST,
                {
                    "task": "Review the following output",
                    "content": result,
                    "original_sender": message.sender,
                },
                correlation_id=correlation_id,
            )

        return Message(
            sender=self.agent_id,
            recipient="user",
            type=MessageType.TASK_RESULT,
            payload={"status": "complete", "result": result},
            correlation_id=correlation_id,
        )

    def _handle_error(self, message: Message) -> Message | None:
        error = message.payload.get("error", "Unknown error")
        logger.error("Error from %s: %s", message.sender, error)

        if self.memory:
            self.memory.remember(
                f"Error from {message.sender}: {error}",
                category="error",
                persist=True,
                collection="bugs",
            )

        return self.send(
            "debugger",
            MessageType.TASK_REQUEST,
            {
                "task": f"Investigate and fix error: {error}",
                "source_agent": message.sender,
                "error_details": message.payload,
            },
            correlation_id=message.correlation_id,
        )
