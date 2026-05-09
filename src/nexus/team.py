"""Team assembly — wires up all agents into a working system."""

from __future__ import annotations

import logging
from typing import Any

from nexus.agents.backend_developer import BackendDeveloperAgent
from nexus.agents.critic import CriticAgent
from nexus.agents.debugger import DebuggerAgent
from nexus.agents.frontend_developer import FrontendDeveloperAgent
from nexus.agents.memory_agent import MemoryAgentImpl
from nexus.agents.orchestrator import OrchestratorAgent
from nexus.agents.planner import PlannerAgent
from nexus.agents.qa import QAAgent
from nexus.agents.research import ResearchAgent
from nexus.agents.tool_executor import ToolExecutorAgent
from nexus.agents.ux_ui_designer import UxUiDesignerAgent
from nexus.config import NO_LLM_ROLES, NVIDIA_AGENT_MODELS, NexusConfig
from nexus.core.crew import CrewAssembler
from nexus.core.loop import AgentLoop
from nexus.core.message import Message, MessageBus, MessageType
from nexus.core.registry import AgentRegistry
from nexus.core.repo import RepoIntelligence
from nexus.core.state import CheckpointManager, TaskGraph
from nexus.core.workflow import WorkflowEngine, WorkflowGraph
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
        self._agent_llms: dict[str, LLMProvider] = {}
        self._results: list[dict[str, Any]] = []

        # Orchestration upgrades
        self.checkpoint_mgr = CheckpointManager(
            state_dir=self.config.project_dir + "/.nexus_state",
        )
        self.task_graph = TaskGraph(self.checkpoint_mgr)
        self.crew_assembler = CrewAssembler()
        self.workflow_graph = WorkflowGraph.create_default()

        self._init_llms()
        self._init_agents()

        # Set available agents for crew assembler
        self.crew_assembler.set_available_agents(
            [a.agent_id for a in self.registry.all_agents()]
        )

    def _create_llm(self, model: str) -> LLMProvider | None:
        """Create a provider instance for a specific model."""
        if not self.config.llm.api_key:
            return None
        try:
            return create_provider(
                provider=self.config.llm.provider,
                api_key=self.config.llm.api_key,
                model=model,
            )
        except Exception as e:
            logger.warning("Failed to create LLM for model %s: %s", model, e)
            return None

    def _init_llms(self) -> None:
        """Initialize per-agent LLM providers with role-specific models.

        Iterates through every ``AgentRole`` and assigns an LLM provider:
        * Roles listed in ``NO_LLM_ROLES`` (memory, tool_executor) are skipped.
        * For the *nvidia* provider, the role-specific model from
          ``NVIDIA_AGENT_MODELS`` is attempted first.
        * If the role has no dedicated model **or** model creation fails, the
          default model (``self.config.llm.model``) is used as a fallback.
        * This guarantees every active role gets a working LLM when an API key
          is configured.
        """
        if not self.config.llm.api_key:
            logger.info("No API key configured — agents will use rule-based fallbacks")
            return

        from nexus.core.agent import AgentRole

        default_model = self.config.llm.model
        is_nvidia = self.config.llm.provider == "nvidia"

        for role in AgentRole:
            role_name: str = role.value

            if role_name in NO_LLM_ROLES:
                continue

            llm: LLMProvider | None = None

            # Try role-specific model when using nvidia provider
            if is_nvidia:
                specific_model = NVIDIA_AGENT_MODELS.get(role_name)
                if specific_model:
                    llm = self._create_llm(specific_model)
                    if llm:
                        self._agent_llms[role_name] = llm
                        logger.info("LLM for %s: %s", role_name, specific_model)
                        continue
                    logger.warning(
                        "Role-specific model %s failed for %s, falling back to default",
                        specific_model,
                        role_name,
                    )

            # Fallback to default model
            llm = self._create_llm(default_model)
            if llm:
                self._agent_llms[role_name] = llm
                logger.info("LLM for %s: %s (fallback)", role_name, default_model)
            else:
                logger.error("Failed to create any LLM for role %s", role_name)

    def _llm_for(self, role: str) -> LLMProvider | None:
        return self._agent_llms.get(role)

    def _init_agents(self) -> None:
        orchestrator = OrchestratorAgent(
            "orchestrator", self.bus,
            llm=self._llm_for("orchestrator"),
            memory=self.memory,
        )
        planner = PlannerAgent(
            "planner", self.bus,
            llm=self._llm_for("planner"),
            memory=self.memory,
        )
        frontend_dev = FrontendDeveloperAgent(
            "frontend_developer", self.bus,
            llm=self._llm_for("frontend_developer"),
            memory=self.memory,
            tools=self.tools,
        )
        ux_ui_designer = UxUiDesignerAgent(
            "ux_ui_designer", self.bus,
            llm=self._llm_for("ux_ui_designer"),
            memory=self.memory,
            tools=self.tools,
        )
        backend_dev = BackendDeveloperAgent(
            "backend_developer", self.bus,
            llm=self._llm_for("backend_developer"),
            memory=self.memory,
            tools=self.tools,
        )
        debugger = DebuggerAgent(
            "debugger", self.bus,
            llm=self._llm_for("debugger"),
            memory=self.memory,
            tools=self.tools,
        )
        qa = QAAgent(
            "qa", self.bus,
            llm=self._llm_for("qa"),
            memory=self.memory,
            tools=self.tools,
        )
        research = ResearchAgent(
            "research", self.bus,
            llm=self._llm_for("research"),
            memory=self.memory,
            tools=self.tools,
        )
        memory_agent = MemoryAgentImpl("memory", self.bus, memory=self.memory)
        critic = CriticAgent(
            "critic", self.bus,
            llm=self._llm_for("critic"),
            memory=self.memory,
        )
        tool_exec = ToolExecutorAgent("tool_executor", self.bus, tools=self.tools)

        for agent in [
            orchestrator,
            planner,
            frontend_dev,
            ux_ui_designer,
            backend_dev,
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

        # Inject GitNexus context if available
        if self.config.gitnexus:
            repo_intel = RepoIntelligence(self.config.project_dir)
            context = repo_intel.get_context()
            if context:
                logger.info("Loading GitNexus project intelligence...")
                self.memory.remember(
                    context,
                    category="project_intelligence"
                )

        # Analyze crew requirements
        crew = self.crew_assembler.assemble(user_request)
        logger.info(
            "Crew assembled: category=%s, agents=%s, parallel=%s",
            crew.category.value,
            crew.agents,
            crew.parallel,
        )

        initial_message = Message(
            sender="user",
            recipient="orchestrator",
            type=MessageType.TASK_REQUEST,
            payload={
                "task": user_request,
                "crew": {
                    "category": crew.category.value,
                    "agents": crew.agents,
                    "parallel": crew.parallel,
                    "reasoning": crew.reasoning,
                },
            },
        )

        loop = AgentLoop(self.registry, bus=self.bus, max_iterations=self.config.max_iterations)
        state = loop.run(initial_message)

        result: dict[str, Any] = {
            "completed": state.completed,
            "iterations": state.iteration,
            "results": state.results,
            "errors": state.errors,
            "crew": {
                "category": crew.category.value,
                "agents": crew.agents,
            },
            "task_graph": self.task_graph.summary(),
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

    def run_workflow(self, user_request: str) -> dict[str, Any]:
        """Process a complex request using the full workflow engine.

        Use this for multi-phase tasks (plan→design→code→test→review).
        For simpler tasks, ``run()`` with the linear loop is sufficient.
        """
        logger.info("Workflow request: %s", user_request[:100])

        self.memory.remember(
            f"Workflow request: {user_request}",
            category="user_input",
        )

        engine = WorkflowEngine(
            registry=self.registry,
            graph=self.workflow_graph,
            task_graph=self.task_graph,
            max_iterations=self.config.max_iterations,
        )
        wf_state = engine.run(user_request)
        summary = engine.get_phase_summary()

        # Collect output from the last successful phase
        final_output = ""
        for phase_name in reversed(wf_state.completed_phases):
            phase_data = wf_state.phase_results.get(phase_name, {})
            outputs = phase_data.get("outputs", [])
            for out in reversed(outputs):
                result_val = out.get("result", "")
                if result_val:
                    final_output = str(result_val)[:2000]
                    break
            if final_output:
                break

        result: dict[str, Any] = {
            "completed": wf_state.completed,
            "iterations": wf_state.iteration,
            "phases": summary["phases"],
            "errors": wf_state.errors,
            "output": final_output or "Workflow completed.",
            "task_graph": self.task_graph.summary(),
        }
        self._results.append(result)
        return result

    @property
    def agent_count(self) -> int:
        return len(self.registry)
