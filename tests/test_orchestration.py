"""Tests for the orchestration upgrade: state machine, parallel execution,
workflow engine, and dynamic crew assembly."""

from __future__ import annotations

import tempfile

import pytest

from nexus.core.agent import Agent, AgentRole
from nexus.core.crew import (
    CREW_TEMPLATES,
    CrewAssembler,
    CrewTemplate,
    TaskCategory,
)
from nexus.core.message import Message, MessageBus, MessageType
from nexus.core.parallel import ParallelExecutionEngine, ParallelTask
from nexus.core.registry import AgentRegistry
from nexus.core.state import (
    CheckpointManager,
    InvalidTransitionError,
    TaskGraph,
    TaskState,
    TaskStatus,
)
from nexus.core.workflow import (
    WorkflowEngine,
    WorkflowGraph,
    WorkflowPhase,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class EchoAgent(Agent):
    """Simple agent that echoes back task requests."""

    def process(self, message: Message) -> Message | None:
        if message.type == MessageType.TASK_REQUEST:
            return message.reply(
                MessageType.TASK_RESULT,
                {
                    "status": "complete",
                    "result": f"Done by {self.agent_id}: {message.payload.get('task', '')}",
                },
            )
        return None


class SlowAgent(Agent):
    """Agent that simulates slow processing."""

    def process(self, message: Message) -> Message | None:
        import time
        time.sleep(0.05)
        return message.reply(
            MessageType.TASK_RESULT,
            {"status": "complete", "result": f"Slow: {self.agent_id}"},
        )


class FailingAgent(Agent):
    """Agent that raises an exception."""

    def process(self, message: Message) -> Message | None:
        raise RuntimeError(f"Agent {self.agent_id} failed intentionally")


def _make_registry_with_agents() -> tuple[AgentRegistry, MessageBus]:
    """Create a registry with echo agents for all standard roles."""
    bus = MessageBus()
    registry = AgentRegistry()
    agents = [
        EchoAgent("orchestrator", AgentRole.ORCHESTRATOR, bus),
        EchoAgent("planner", AgentRole.PLANNER, bus),
        EchoAgent("frontend_developer", AgentRole.FRONTEND_DEVELOPER, bus),
        EchoAgent("backend_developer", AgentRole.BACKEND_DEVELOPER, bus),
        EchoAgent("ux_ui_designer", AgentRole.UX_UI_DESIGNER, bus),
        EchoAgent("debugger", AgentRole.DEBUGGER, bus),
        EchoAgent("qa", AgentRole.QA, bus),
        EchoAgent("research", AgentRole.RESEARCH, bus),
        EchoAgent("critic", AgentRole.CRITIC, bus),
    ]
    for a in agents:
        registry.register(a)
    return registry, bus


# ===========================================================================
# 1. State Machine & Checkpointing
# ===========================================================================


class TestTaskStatus:
    def test_valid_transition(self) -> None:
        task = TaskState(task_id="t1", description="test task")
        assert task.status == TaskStatus.PENDING
        task.transition(TaskStatus.IN_PROGRESS, agent_id="dev", reason="starting")
        assert task.status == TaskStatus.IN_PROGRESS
        assert len(task.history) == 1
        assert task.history[0]["from_status"] == "pending"
        assert task.history[0]["to_status"] == "in_progress"

    def test_invalid_transition_raises(self) -> None:
        task = TaskState(task_id="t2", description="test")
        task.transition(TaskStatus.COMPLETED)
        with pytest.raises(InvalidTransitionError):
            task.transition(TaskStatus.IN_PROGRESS)

    def test_is_terminal(self) -> None:
        task = TaskState(task_id="t3", description="test")
        assert not task.is_terminal
        task.transition(TaskStatus.COMPLETED)
        assert task.is_terminal

    def test_can_retry(self) -> None:
        task = TaskState(task_id="t4", description="test", max_retries=2)
        assert task.can_retry
        task.retry_count = 2
        assert not task.can_retry

    def test_to_dict_and_from_dict(self) -> None:
        task = TaskState(
            task_id="t5",
            description="roundtrip",
            metadata={"key": "value"},
        )
        task.transition(TaskStatus.IN_PROGRESS)
        data = task.to_dict()
        restored = TaskState.from_dict(data)
        assert restored.task_id == "t5"
        assert restored.status == TaskStatus.IN_PROGRESS
        assert restored.metadata["key"] == "value"
        assert len(restored.history) == 1

    def test_full_lifecycle(self) -> None:
        task = TaskState(task_id="t6", description="lifecycle")
        task.transition(TaskStatus.PLANNING)
        task.transition(TaskStatus.DELEGATED)
        task.transition(TaskStatus.IN_PROGRESS)
        task.transition(TaskStatus.REVIEWING)
        task.transition(TaskStatus.COMPLETED)
        assert len(task.history) == 5


class TestCheckpointManager:
    def test_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(state_dir=tmp)
            tasks = {
                "t1": TaskState(task_id="t1", description="task 1"),
                "t2": TaskState(task_id="t2", description="task 2"),
            }
            tasks["t1"].transition(TaskStatus.IN_PROGRESS)
            mgr.save(tasks, iteration=1)

            loaded = mgr.load_latest()
            assert loaded is not None
            assert "t1" in loaded.tasks
            assert loaded.tasks["t1"]["status"] == "in_progress"
            assert loaded.iteration == 1

    def test_restore_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(state_dir=tmp)
            tasks = {"t1": TaskState(task_id="t1", description="restore test")}
            cp = mgr.save(tasks)
            restored = mgr.restore_tasks(cp)
            assert "t1" in restored
            assert restored["t1"].description == "restore test"

    def test_list_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(state_dir=tmp)
            tasks = {"t1": TaskState(task_id="t1", description="x")}
            for i in range(7):
                mgr.save(tasks, iteration=i)
            cps = mgr.list_checkpoints()
            assert len(cps) == 7
            removed = mgr.cleanup(keep=3)
            assert removed == 4
            assert len(mgr.list_checkpoints()) == 3

    def test_load_latest_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(state_dir=tmp)
            assert mgr.load_latest() is None


class TestTaskGraph:
    def test_add_and_get_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            graph = TaskGraph(CheckpointManager(state_dir=tmp))
            task = graph.add_task("build frontend", task_id="t1")
            assert graph.get_task("t1") is task
            assert graph.get_task("nonexistent") is None

    def test_parent_child_relationship(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            graph = TaskGraph(CheckpointManager(state_dir=tmp))
            parent = graph.add_task("main task", task_id="parent")
            child = graph.add_task("subtask", task_id="child", parent_id="parent")
            assert child.parent_task_id == "parent"
            assert "child" in parent.subtask_ids

    def test_dependency_tracking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            graph = TaskGraph(CheckpointManager(state_dir=tmp))
            graph.add_task("plan", task_id="t1")
            graph.add_task("code", task_id="t2", dependencies=["t1"])
            graph.add_task("test", task_id="t3", dependencies=["t2"])

            ready = graph.get_ready_tasks()
            assert len(ready) == 1
            assert ready[0].task_id == "t1"

            graph.transition_task("t1", TaskStatus.COMPLETED, auto_checkpoint=False)
            ready = graph.get_ready_tasks()
            assert len(ready) == 1
            assert ready[0].task_id == "t2"

    def test_all_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            graph = TaskGraph(CheckpointManager(state_dir=tmp))
            graph.add_task("t1", task_id="t1")
            graph.add_task("t2", task_id="t2")
            assert not graph.all_completed()

            graph.transition_task("t1", TaskStatus.COMPLETED, auto_checkpoint=False)
            assert not graph.all_completed()

            graph.transition_task("t2", TaskStatus.COMPLETED, auto_checkpoint=False)
            assert graph.all_completed()

    def test_checkpoint_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = CheckpointManager(state_dir=tmp)
            graph = TaskGraph(mgr)
            graph.add_task("task A", task_id="a")
            graph.transition_task("a", TaskStatus.IN_PROGRESS, auto_checkpoint=False)
            graph.checkpoint()

            graph2 = TaskGraph(mgr)
            assert graph2.restore()
            assert graph2.get_task("a") is not None
            assert graph2.get_task("a").status == TaskStatus.IN_PROGRESS  # type: ignore[union-attr]

    def test_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            graph = TaskGraph(CheckpointManager(state_dir=tmp))
            graph.add_task("a", task_id="a")
            graph.add_task("b", task_id="b")
            graph.transition_task("a", TaskStatus.COMPLETED, auto_checkpoint=False)
            s = graph.summary()
            assert s["total"] == 2
            assert s["by_status"]["completed"] == 1
            assert s["by_status"]["pending"] == 1


# ===========================================================================
# 2. Parallel Execution Engine
# ===========================================================================


class TestParallelEngine:
    def test_single_task(self) -> None:
        registry, bus = _make_registry_with_agents()
        engine = ParallelExecutionEngine(registry)
        tasks = [
            ParallelTask(
                task_id="p1",
                agent_id="planner",
                message=Message(
                    sender="orchestrator",
                    recipient="planner",
                    type=MessageType.TASK_REQUEST,
                    payload={"task": "plan something"},
                ),
            )
        ]
        results = engine.execute(tasks)
        assert len(results) == 1
        assert results[0].success
        assert results[0].response is not None

    def test_parallel_independent_tasks(self) -> None:
        registry, bus = _make_registry_with_agents()
        engine = ParallelExecutionEngine(registry, max_workers=3)
        tasks = [
            ParallelTask(
                task_id=f"p{i}",
                agent_id=agent,
                message=Message(
                    sender="orchestrator",
                    recipient=agent,
                    type=MessageType.TASK_REQUEST,
                    payload={"task": f"do {agent} work"},
                ),
            )
            for i, agent in enumerate(
                ["frontend_developer", "backend_developer", "research"]
            )
        ]
        results = engine.execute(tasks)
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_dependency_layers(self) -> None:
        registry, bus = _make_registry_with_agents()
        engine = ParallelExecutionEngine(registry)
        tasks = [
            ParallelTask(
                task_id="plan",
                agent_id="planner",
                message=Message(
                    sender="orchestrator",
                    recipient="planner",
                    type=MessageType.TASK_REQUEST,
                    payload={"task": "plan"},
                ),
            ),
            ParallelTask(
                task_id="code",
                agent_id="frontend_developer",
                message=Message(
                    sender="orchestrator",
                    recipient="frontend_developer",
                    type=MessageType.TASK_REQUEST,
                    payload={"task": "code"},
                ),
                depends_on=["plan"],
            ),
        ]
        results = engine.execute(tasks)
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_missing_agent(self) -> None:
        registry, bus = _make_registry_with_agents()
        engine = ParallelExecutionEngine(registry)
        tasks = [
            ParallelTask(
                task_id="p1",
                agent_id="nonexistent_agent",
                message=Message(
                    sender="orchestrator",
                    recipient="nonexistent_agent",
                    type=MessageType.TASK_REQUEST,
                    payload={"task": "x"},
                ),
            )
        ]
        results = engine.execute(tasks)
        assert len(results) == 1
        assert not results[0].success
        assert "not found" in (results[0].error or "")

    def test_failing_task(self) -> None:
        bus = MessageBus()
        registry = AgentRegistry()
        registry.register(FailingAgent("fail_agent", AgentRole.DEVELOPER, bus))
        engine = ParallelExecutionEngine(registry)
        tasks = [
            ParallelTask(
                task_id="p1",
                agent_id="fail_agent",
                message=Message(
                    sender="orchestrator",
                    recipient="fail_agent",
                    type=MessageType.TASK_REQUEST,
                    payload={"task": "crash"},
                ),
            )
        ]
        results = engine.execute(tasks)
        assert len(results) == 1
        assert not results[0].success
        assert results[0].duration_ms >= 0

    def test_detect_parallelizable(self) -> None:
        registry, bus = _make_registry_with_agents()
        engine = ParallelExecutionEngine(registry)
        subtasks = [
            {"task": "build UI", "agent": "frontend_developer", "id": "fe"},
            {"task": "build API", "agent": "backend_developer", "id": "be"},
            {"task": "test all", "agent": "qa", "id": "qa", "depends_on": ["fe", "be"]},
        ]
        ptasks = engine.detect_parallelizable(subtasks)
        assert len(ptasks) == 3
        assert ptasks[2].depends_on == ["fe", "be"]

    def test_empty_task_list(self) -> None:
        registry, bus = _make_registry_with_agents()
        engine = ParallelExecutionEngine(registry)
        results = engine.execute([])
        assert results == []


# ===========================================================================
# 3. Workflow Graph & Engine
# ===========================================================================


class TestWorkflowGraph:
    def test_default_graph(self) -> None:
        graph = WorkflowGraph.create_default()
        assert len(graph.nodes) == 5
        assert WorkflowPhase.PLAN in graph.nodes
        assert WorkflowPhase.CODE in graph.nodes
        entry = graph.get_entry_phase()
        assert entry == WorkflowPhase.PLAN

    def test_add_nodes_and_edges(self) -> None:
        graph = WorkflowGraph()
        graph.add_node(WorkflowPhase.PLAN)
        graph.add_node(WorkflowPhase.CODE)
        graph.add_edge(WorkflowPhase.PLAN, WorkflowPhase.CODE)

        successors = graph.get_successors(WorkflowPhase.PLAN)
        assert WorkflowPhase.CODE in successors

    def test_entry_phase(self) -> None:
        graph = WorkflowGraph()
        graph.add_node(WorkflowPhase.PLAN)
        graph.add_node(WorkflowPhase.CODE)
        graph.add_edge(WorkflowPhase.PLAN, WorkflowPhase.CODE)
        assert graph.get_entry_phase() == WorkflowPhase.PLAN

    def test_custom_agents_per_phase(self) -> None:
        graph = WorkflowGraph()
        node = graph.add_node(
            WorkflowPhase.CODE,
            agents=["frontend_developer", "backend_developer", "research"],
            parallel=True,
        )
        assert len(node.agents) == 3
        assert node.parallel

    def test_empty_graph(self) -> None:
        graph = WorkflowGraph()
        assert graph.get_entry_phase() is None


class TestWorkflowEngine:
    def test_basic_workflow(self) -> None:
        registry, bus = _make_registry_with_agents()
        graph = WorkflowGraph()
        graph.add_node(WorkflowPhase.PLAN)
        graph.add_node(WorkflowPhase.CODE, agents=["frontend_developer"])
        graph.add_edge(WorkflowPhase.PLAN, WorkflowPhase.CODE)

        engine = WorkflowEngine(registry, graph=graph, max_iterations=10)
        state = engine.run("Build a login page")

        assert "plan" in state.completed_phases
        assert "code" in state.completed_phases
        assert state.completed

    def test_parallel_phase_execution(self) -> None:
        registry, bus = _make_registry_with_agents()
        graph = WorkflowGraph()
        graph.add_node(
            WorkflowPhase.CODE,
            agents=["frontend_developer", "backend_developer"],
            parallel=True,
        )
        engine = WorkflowEngine(registry, graph=graph)
        state = engine.run("Build full-stack app")
        assert state.completed
        phase_data = state.phase_results.get("code", {})
        assert len(phase_data.get("outputs", [])) == 2

    def test_phase_with_no_agents_skipped(self) -> None:
        registry, _ = _make_registry_with_agents()
        graph = WorkflowGraph()
        graph.add_node(WorkflowPhase.DEPLOY, agents=[])
        engine = WorkflowEngine(registry, graph=graph)
        state = engine.run("Deploy something")
        assert state.completed
        deploy_data = state.phase_results.get("deploy", {})
        assert deploy_data.get("skipped")

    def test_get_phase_summary(self) -> None:
        registry, bus = _make_registry_with_agents()
        graph = WorkflowGraph()
        graph.add_node(WorkflowPhase.PLAN)
        engine = WorkflowEngine(registry, graph=graph)
        engine.run("Plan a project")
        summary = engine.get_phase_summary()
        assert "workflow_id" in summary
        assert "phases" in summary


# ===========================================================================
# 4. Dynamic Crew Assembly
# ===========================================================================


class TestCrewAssembler:
    def test_frontend_task(self) -> None:
        assembler = CrewAssembler()
        result = assembler.analyze_task("Build a React component for user profile")
        assert result == TaskCategory.FRONTEND

    def test_backend_task(self) -> None:
        assembler = CrewAssembler()
        result = assembler.analyze_task("Create a REST API endpoint for authentication")
        assert result == TaskCategory.BACKEND

    def test_fullstack_task(self) -> None:
        assembler = CrewAssembler()
        result = assembler.analyze_task(
            "Build a web app with React frontend and Node.js backend API"
        )
        assert result == TaskCategory.FULL_STACK

    def test_bugfix_task(self) -> None:
        assembler = CrewAssembler()
        result = assembler.analyze_task("Fix the bug in the login error handling")
        assert result == TaskCategory.BUG_FIX

    def test_design_task(self) -> None:
        assembler = CrewAssembler()
        result = assembler.analyze_task("Create a wireframe for the dashboard")
        assert result == TaskCategory.DESIGN

    def test_research_task(self) -> None:
        assembler = CrewAssembler()
        result = assembler.analyze_task("Research best practices for GraphQL caching")
        assert result == TaskCategory.RESEARCH

    def test_general_task(self) -> None:
        assembler = CrewAssembler()
        result = assembler.analyze_task("Do something unrelated to any category xyz")
        assert result == TaskCategory.GENERAL

    def test_assemble_returns_agents(self) -> None:
        assembler = CrewAssembler(available_agents=[
            "orchestrator", "planner", "frontend_developer",
            "backend_developer", "qa", "ux_ui_designer", "critic",
        ])
        assignment = assembler.assemble("Build a React login page")
        assert "orchestrator" in assignment.agents
        assert "frontend_developer" in assignment.agents
        assert assignment.category == TaskCategory.FRONTEND
        assert assignment.confidence > 0

    def test_assemble_fullstack_includes_parallel(self) -> None:
        assembler = CrewAssembler()
        assignment = assembler.assemble(
            "Build a full-stack web app with frontend and backend"
        )
        assert assignment.category == TaskCategory.FULL_STACK
        assert assignment.parallel

    def test_custom_template(self) -> None:
        custom = CrewTemplate(
            category=TaskCategory.GENERAL,
            required_agents=["research", "planner", "critic"],
            description="Custom research crew",
        )
        assembler = CrewAssembler(custom_templates={TaskCategory.GENERAL: custom})
        assignment = assembler.assemble("something unknown")
        assert "research" in assignment.agents
        assert "planner" in assignment.agents

    def test_templates_complete(self) -> None:
        """Every TaskCategory should have a template."""
        for cat in TaskCategory:
            assert cat in CREW_TEMPLATES, f"Missing template for {cat}"


# ===========================================================================
# 5. Integration: Team with orchestration
# ===========================================================================


class TestTeamOrchestration:
    def test_team_has_orchestration_components(self) -> None:
        from nexus.config import NexusConfig
        from nexus.team import NexusTeam

        cfg = NexusConfig()
        team = NexusTeam(cfg)
        assert team.checkpoint_mgr is not None
        assert team.task_graph is not None
        assert team.crew_assembler is not None
        assert team.workflow_graph is not None

    def test_team_run_includes_crew_info(self) -> None:
        from nexus.config import NexusConfig
        from nexus.team import NexusTeam

        cfg = NexusConfig()
        team = NexusTeam(cfg)
        result = team.run("Build a React login component")
        assert "crew" in result
        assert result["crew"]["category"] in [c.value for c in TaskCategory]
        assert "task_graph" in result

    def test_crew_assembler_knows_agents(self) -> None:
        from nexus.config import NexusConfig
        from nexus.team import NexusTeam

        cfg = NexusConfig()
        team = NexusTeam(cfg)
        assignment = team.crew_assembler.assemble("Fix the auth bug")
        assert "debugger" in assignment.agents
