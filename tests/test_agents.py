"""Tests for specialized agents."""

from __future__ import annotations

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
from nexus.core.message import Message, MessageBus, MessageType
from nexus.core.tool import ToolRegistry
from nexus.memory.manager import MemoryManager
from nexus.tools.file_ops import FileReadTool


class TestOrchestratorAgent:
    def test_rule_based_delegation_plan(self) -> None:
        bus = MessageBus()
        agent = OrchestratorAgent("orchestrator", bus)

        msg = Message(
            sender="user",
            recipient="orchestrator",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Plan a new web application"},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.recipient == "planner"
        assert response.type == MessageType.TASK_REQUEST

    def test_rule_based_delegation_debug(self) -> None:
        bus = MessageBus()
        agent = OrchestratorAgent("orchestrator", bus)

        msg = Message(
            sender="user",
            recipient="orchestrator",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Fix the bug in login handler"},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.recipient == "debugger"

    def test_rule_based_delegation_test(self) -> None:
        bus = MessageBus()
        agent = OrchestratorAgent("orchestrator", bus)

        msg = Message(
            sender="user",
            recipient="orchestrator",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Test the API endpoints"},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.recipient == "qa"

    def test_rule_based_delegation_design(self) -> None:
        bus = MessageBus()
        agent = OrchestratorAgent("orchestrator", bus)

        msg = Message(
            sender="user",
            recipient="orchestrator",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Design a prototype for the dashboard"},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.recipient == "ux_ui_designer"

    def test_rule_based_delegation_frontend(self) -> None:
        bus = MessageBus()
        agent = OrchestratorAgent("orchestrator", bus)

        msg = Message(
            sender="user",
            recipient="orchestrator",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Build a React login component with CSS"},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.recipient == "frontend_developer"

    def test_rule_based_delegation_backend(self) -> None:
        bus = MessageBus()
        agent = OrchestratorAgent("orchestrator", bus)

        msg = Message(
            sender="user",
            recipient="orchestrator",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Create a REST API endpoint for user management"},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.recipient == "backend_developer"

    def test_handle_task_result(self) -> None:
        bus = MessageBus()
        agent = OrchestratorAgent("orchestrator", bus)

        msg = Message(
            sender="developer",
            recipient="orchestrator",
            type=MessageType.TASK_RESULT,
            payload={"status": "complete", "result": "Feature implemented"},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.type == MessageType.TASK_RESULT
        assert response.payload["status"] == "complete"

    def test_handle_error_delegates_to_debugger(self) -> None:
        bus = MessageBus()
        agent = OrchestratorAgent("orchestrator", bus)

        msg = Message(
            sender="developer",
            recipient="orchestrator",
            type=MessageType.ERROR,
            payload={"error": "TypeError: undefined is not a function"},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.recipient == "debugger"


class TestPlannerAgent:
    def test_rule_based_plan(self) -> None:
        bus = MessageBus()
        agent = PlannerAgent("planner", bus)

        msg = Message(
            sender="orchestrator",
            recipient="planner",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Build a REST API", "context": ""},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.type == MessageType.TASK_RESULT
        plan = response.payload.get("plan", {})
        assert "steps" in plan
        assert len(plan["steps"]) > 0
        assert "milestones" in plan

    def test_ignores_non_task_messages(self) -> None:
        bus = MessageBus()
        agent = PlannerAgent("planner", bus)

        msg = Message(
            sender="orchestrator",
            recipient="planner",
            type=MessageType.STATUS,
            payload={},
        )
        response = agent.process(msg)
        assert response is None


class TestUxUiDesignerAgent:
    def test_stub_design_direction(self) -> None:
        bus = MessageBus()
        agent = UxUiDesignerAgent("ux_ui_designer", bus)

        msg = Message(
            sender="orchestrator",
            recipient="ux_ui_designer",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Design a visual style for the landing page", "context": ""},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.type == MessageType.TASK_RESULT
        assert response.payload["status"] == "needs_review"
        result = response.payload.get("result", {})
        assert result.get("action") == "recommend_directions"
        assert len(result.get("directions", [])) == 3

    def test_stub_specific_design(self) -> None:
        bus = MessageBus()
        agent = UxUiDesignerAgent("ux_ui_designer", bus)

        msg = Message(
            sender="orchestrator",
            recipient="ux_ui_designer",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Create a prototype for a mobile login screen", "context": ""},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.type == MessageType.TASK_RESULT
        result = response.payload.get("result", {})
        assert result.get("action") == "complete"
        assert "design_spec" in result
        assert "suggestions" in result

    def test_ignores_non_task_messages(self) -> None:
        bus = MessageBus()
        agent = UxUiDesignerAgent("ux_ui_designer", bus)

        msg = Message(
            sender="orchestrator",
            recipient="ux_ui_designer",
            type=MessageType.EVENT,
            payload={"event": "some_event"},
        )
        response = agent.process(msg)
        assert response is None


class TestFrontendDeveloperAgent:
    def test_stub_response(self) -> None:
        bus = MessageBus()
        agent = FrontendDeveloperAgent("frontend_developer", bus)

        msg = Message(
            sender="orchestrator",
            recipient="frontend_developer",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Build a login form component", "context": ""},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.type == MessageType.TASK_RESULT
        assert response.payload["status"] == "needs_review"
        result = response.payload.get("result", {})
        assert "suggestions" in result


class TestBackendDeveloperAgent:
    def test_stub_response(self) -> None:
        bus = MessageBus()
        agent = BackendDeveloperAgent("backend_developer", bus)

        msg = Message(
            sender="orchestrator",
            recipient="backend_developer",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Build a REST API for users", "context": ""},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.type == MessageType.TASK_RESULT
        assert response.payload["status"] == "needs_review"
        result = response.payload.get("result", {})
        assert "suggestions" in result


class TestDebuggerAgent:
    def test_stub_diagnosis(self) -> None:
        bus = MessageBus()
        agent = DebuggerAgent("debugger", bus)

        msg = Message(
            sender="orchestrator",
            recipient="debugger",
            type=MessageType.TASK_REQUEST,
            payload={
                "task": "Fix null pointer error",
                "error_details": {"traceback": "NoneType has no attribute 'id'"},
            },
        )
        response = agent.process(msg)

        assert response is not None
        assert response.type == MessageType.TASK_RESULT


class TestQAAgent:
    def test_stub_qa(self) -> None:
        bus = MessageBus()
        agent = QAAgent("qa", bus)

        msg = Message(
            sender="orchestrator",
            recipient="qa",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Test user login", "content": ""},
        )
        response = agent.process(msg)

        assert response is not None
        assert "results" in response.payload.get("result", {})


class TestResearchAgent:
    def test_stub_research(self) -> None:
        bus = MessageBus()
        agent = ResearchAgent("research", bus)

        msg = Message(
            sender="orchestrator",
            recipient="research",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Research authentication best practices"},
        )
        response = agent.process(msg)

        assert response is not None
        result = response.payload.get("result", {})
        assert "findings" in result


class TestMemoryAgentImpl:
    def test_query(self) -> None:
        bus = MessageBus()
        memory = MemoryManager(persist_dir="/tmp/test_mem_agent")
        memory.remember("Python async patterns", category="code")

        agent = MemoryAgentImpl("memory", bus, memory=memory)

        msg = Message(
            sender="developer",
            recipient="memory",
            type=MessageType.QUERY,
            payload={"query": "async"},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.type == MessageType.TASK_RESULT

    def test_store_request(self) -> None:
        bus = MessageBus()
        memory = MemoryManager(persist_dir="/tmp/test_mem_agent2")

        agent = MemoryAgentImpl("memory", bus, memory=memory)

        msg = Message(
            sender="critic",
            recipient="memory",
            type=MessageType.TASK_REQUEST,
            payload={
                "content": "Always validate inputs",
                "collection": "reflections",
                "category": "lesson",
            },
        )
        response = agent.process(msg)

        assert response is not None
        assert response.payload.get("result", {}).get("stored_id") is not None


class TestCriticAgent:
    def test_stub_evaluation(self) -> None:
        bus = MessageBus()
        agent = CriticAgent("critic", bus)

        msg = Message(
            sender="orchestrator",
            recipient="critic",
            type=MessageType.TASK_REQUEST,
            payload={
                "task": "Evaluate authentication module",
                "content": "def login(user, password): return check_credentials(user, password)",
            },
        )
        response = agent.process(msg)

        assert response is not None
        result = response.payload.get("result", {})
        assert "overall_score" in result
        assert "verdict" in result
        assert result["verdict"] in ("approve", "revise")


class TestToolExecutorAgent:
    def test_execute_known_tool(self) -> None:
        bus = MessageBus()
        tools = ToolRegistry()
        tools.register(FileReadTool())

        agent = ToolExecutorAgent("tool_executor", bus, tools=tools)

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content")
            path = f.name

        try:
            msg = Message(
                sender="developer",
                recipient="tool_executor",
                type=MessageType.TASK_REQUEST,
                payload={"tool": "file_read", "params": {"path": path}},
            )
            response = agent.process(msg)

            assert response is not None
            assert response.payload["status"] == "complete"
            assert response.payload["result"]["output"] == "test content"
        finally:
            import os
            os.unlink(path)

    def test_unknown_tool(self) -> None:
        bus = MessageBus()
        agent = ToolExecutorAgent("tool_executor", bus, tools=ToolRegistry())

        msg = Message(
            sender="developer",
            recipient="tool_executor",
            type=MessageType.TASK_REQUEST,
            payload={"tool": "nonexistent", "params": {}},
        )
        response = agent.process(msg)

        assert response is not None
        assert response.type == MessageType.ERROR
