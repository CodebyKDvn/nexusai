"""Team assembly — wires up all agents into a working system."""

from __future__ import annotations

import logging
from typing import Any

from nexus.agents.critic import CriticAgent
from nexus.agents.debugger import DebuggerAgent
from nexus.agents.developer import DeveloperAgent
from nexus.agents.memory_agent import MemoryAgentImpl
from nexus.agents.orchestrator import OrchestratorAgent
from nexus.agents.planner import PlannerAgent
from nexus.agents.qa import QAAgent
from nexus.agents.research import ResearchAgent
from nexus.agents.tool_executor import ToolExecutorAgent
from nexus.config import NexusConfig
from nexus.core.loop import AgentLoop
from nexus.core.message import Message, MessageBus, MessageType
from nexus.core.registry import AgentRegistry
from nexus.llm.provider import LLMProvider, create_provider
from nexus.memory.manager import MemoryManager
from nexus.tools import create_default_registry

logger = logging.getLogger(__name__)


class NexusTeam:
    """Assembles and manages the full AI dev team."""

    def __init__(self, config: NexusConfig | None = None) -> None:
        self.config = config or NexusConfig()
        self.bus = MessageBus()
        self.registry = AgentRegistry()
        self.memory = MemoryManager(
            persist_dir=self.config.memory.persist_dir,
            short_term_capacity=self.config.memory.short_term_capacity,
        )
        self.tools = create_default_registry()
        self.llm: LLMProvider | None = None
        self._results: list[dict[str, Any]] = []

        self._init_llm()
        self._init_agents()

    def _init_llm(self) -> None:
        if self.config.llm.api_key:
            try:
                self.llm = create_provider(
                    provider=self.config.llm.provider,
                    api_key=self.config.llm.api_key,
                    model=self.config.llm.model,
                )
                logger.info(
                    "LLM provider initialized: %s/%s",
                    self.config.llm.provider,
                    self.config.llm.model,
                )
            except Exception as e:
                logger.warning("Failed to initialize LLM: %s", e)
        else:
            logger.info("No API key configured — agents will use rule-based fallbacks")

    def _init_agents(self) -> None:
        orchestrator = OrchestratorAgent(
            "orchestrator", self.bus, llm=self.llm, memory=self.memory
        )
        planner = PlannerAgent("planner", self.bus, llm=self.llm, memory=self.memory)
        developer = DeveloperAgent(
            "developer",
            self.bus,
            llm=self.llm,
            memory=self.memory,
            tools=self.tools,
            specialty="fullstack",
        )
        debugger = DebuggerAgent(
            "debugger", self.bus, llm=self.llm, memory=self.memory, tools=self.tools
        )
        qa = QAAgent("qa", self.bus, llm=self.llm, memory=self.memory, tools=self.tools)
        research = ResearchAgent(
            "research", self.bus, llm=self.llm, memory=self.memory, tools=self.tools
        )
        memory_agent = MemoryAgentImpl("memory", self.bus, memory=self.memory)
        critic = CriticAgent("critic", self.bus, llm=self.llm, memory=self.memory)
        tool_exec = ToolExecutorAgent("tool_executor", self.bus, tools=self.tools)

        for agent in [
            orchestrator,
            planner,
            developer,
            debugger,
            qa,
            research,
            memory_agent,
            critic,
            tool_exec,
        ]:
            self.registry.register(agent)

    def run(self, user_request: str) -> dict[str, Any]:
        """Process a user request through the agent team."""
        logger.info("Processing request: %s", user_request[:100])

        self.memory.remember(
            f"User request: {user_request}",
            category="user_input",
        )

        initial_message = Message(
            sender="user",
            recipient="orchestrator",
            type=MessageType.TASK_REQUEST,
            payload={"task": user_request},
        )

        loop = AgentLoop(self.registry, max_iterations=self.config.max_iterations)
        state = loop.run(initial_message)

        result = {
            "completed": state.completed,
            "iterations": state.iteration,
            "results": state.results,
            "errors": state.errors,
        }

        final_output = ""
        for r in reversed(state.results):
            payload = r.get("payload", {})
            if payload.get("status") == "complete" and payload.get("result"):
                res = payload["result"]
                if isinstance(res, str):
                    final_output = res
                elif isinstance(res, dict):
                    final_output = str(res.get("summary") or res.get("findings") or res)
                break

        result["output"] = final_output or "Task completed."
        self._results.append(result)

        return result

    @property
    def agent_count(self) -> int:
        return len(self.registry)
