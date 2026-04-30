"""Tests for the team assembly and end-to-end flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from nexus.config import NO_LLM_ROLES, NVIDIA_AGENT_MODELS, NexusConfig
from nexus.core.agent import AgentRole
from nexus.team import NexusTeam


class TestNexusTeam:
    def test_initialization(self) -> None:
        config = NexusConfig()
        team = NexusTeam(config)

        assert team.agent_count == 11
        assert team.memory is not None
        assert team.tools is not None

    def test_run_planning_task(self) -> None:
        config = NexusConfig()
        team = NexusTeam(config)

        result = team.run("Plan a REST API for user management")

        assert result["completed"]
        assert result["iterations"] >= 1
        assert "output" in result

    def test_run_debug_task(self) -> None:
        config = NexusConfig()
        team = NexusTeam(config)

        result = team.run("Fix the bug in the login handler")

        assert result["completed"]
        assert "output" in result

    def test_run_test_task(self) -> None:
        config = NexusConfig()
        team = NexusTeam(config)

        result = team.run("Test the user registration flow")

        assert result["completed"]

    def test_run_research_task(self) -> None:
        config = NexusConfig()
        team = NexusTeam(config)

        result = team.run("Research best practices for API authentication")

        assert result["completed"]

    def test_run_review_task(self) -> None:
        config = NexusConfig()
        team = NexusTeam(config)

        result = team.run("Review the current codebase quality")

        assert result["completed"]

    def test_run_frontend_task(self) -> None:
        config = NexusConfig()
        team = NexusTeam(config)

        result = team.run("Build a React login component")

        assert result["completed"]
        assert "output" in result

    def test_run_backend_task(self) -> None:
        config = NexusConfig()
        team = NexusTeam(config)

        result = team.run("Create a REST API endpoint for users")

        assert result["completed"]
        assert "output" in result

    def test_run_design_task(self) -> None:
        config = NexusConfig()
        team = NexusTeam(config)

        result = team.run("Design a prototype for the user dashboard")

        assert result["completed"]
        assert "output" in result

    def test_run_generic_task(self) -> None:
        config = NexusConfig()
        team = NexusTeam(config)

        result = team.run("Build a todo app")

        assert result["completed"]
        assert "output" in result


class TestNexusConfig:
    def test_default_config(self) -> None:
        config = NexusConfig()
        assert config.llm.provider == "nvidia"
        assert config.llm.model == "deepseek-ai/deepseek-v4-pro"
        assert config.max_iterations == 20

    def test_save_and_load(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        config = NexusConfig()
        config.llm.provider = "anthropic"
        config.llm.model = "claude-sonnet-4-20250514"
        config.max_iterations = 30

        config_path = tmp_path / "config.yaml"
        config.save(config_path)

        loaded = NexusConfig.load(config_path)
        assert loaded.llm.provider == "anthropic"
        assert loaded.llm.model == "claude-sonnet-4-20250514"
        assert loaded.max_iterations == 30


class TestNvidiaAgentModels:
    """Tests for NVIDIA_AGENT_MODELS configuration correctness."""

    def test_model_names_spelling(self) -> None:
        assert NVIDIA_AGENT_MODELS["orchestrator"] == "moonshotai/kimi-k2-instruct"
        assert NVIDIA_AGENT_MODELS["planner"] == "z-ai/glm-5.1"
        assert NVIDIA_AGENT_MODELS["ux_ui_designer"] == "moonshotai/kimi-k2-instruct"

    def test_lead_developer_and_developer_present(self) -> None:
        assert "lead_developer" in NVIDIA_AGENT_MODELS
        assert NVIDIA_AGENT_MODELS["lead_developer"] == "deepseek-ai/deepseek-v4-pro"
        assert "developer" in NVIDIA_AGENT_MODELS
        assert NVIDIA_AGENT_MODELS["developer"] == "deepseek-ai/deepseek-v4-flash"

    def test_no_llm_roles_defined(self) -> None:
        assert "memory" in NO_LLM_ROLES
        assert "tool_executor" in NO_LLM_ROLES
        assert "lead_developer" in NO_LLM_ROLES
        assert "developer" in NO_LLM_ROLES


class TestLLMInitialization:
    """Tests for _init_llms robustness and fallback logic."""

    def test_no_api_key_skips_initialization(self) -> None:
        config = NexusConfig()
        config.llm.api_key = ""
        team = NexusTeam(config)
        assert len(team._agent_llms) == 0

    @patch("nexus.team.create_provider")
    def test_nvidia_assigns_all_active_roles(self, mock_create: MagicMock) -> None:
        mock_provider = MagicMock()
        mock_create.return_value = mock_provider

        config = NexusConfig()
        config.llm.provider = "nvidia"
        config.llm.api_key = "test-key"
        team = NexusTeam(config)

        active_roles = {r.value for r in AgentRole} - NO_LLM_ROLES
        for role in active_roles:
            assert role in team._agent_llms, f"Role {role} missing from _agent_llms"

    @patch("nexus.team.create_provider")
    def test_memory_and_tool_executor_excluded(self, mock_create: MagicMock) -> None:
        mock_create.return_value = MagicMock()

        config = NexusConfig()
        config.llm.provider = "nvidia"
        config.llm.api_key = "test-key"
        team = NexusTeam(config)

        assert "memory" not in team._agent_llms
        assert "tool_executor" not in team._agent_llms
        assert "lead_developer" not in team._agent_llms
        assert "developer" not in team._agent_llms

    @patch("nexus.team.create_provider")
    def test_fallback_when_specific_model_fails(self, mock_create: MagicMock) -> None:
        """If a role-specific model fails, fallback to default model."""
        call_count = 0

        def side_effect(provider: str, api_key: str, model: str) -> MagicMock | None:
            nonlocal call_count
            call_count += 1
            # Fail for the first model (orchestrator's kimi-k2-instruct), succeed for default
            if model == "moonshotai/kimi-k2-instruct":
                raise RuntimeError("Model unavailable")
            return MagicMock()

        mock_create.side_effect = side_effect

        config = NexusConfig()
        config.llm.provider = "nvidia"
        config.llm.api_key = "test-key"
        team = NexusTeam(config)

        # orchestrator should still have an LLM (fallback to default)
        assert "orchestrator" in team._agent_llms

    @patch("nexus.team.create_provider")
    def test_non_nvidia_provider_uses_default_model(
        self, mock_create: MagicMock,
    ) -> None:
        mock_provider = MagicMock()
        mock_create.return_value = mock_provider

        config = NexusConfig()
        config.llm.provider = "openai"
        config.llm.api_key = "test-key"
        config.llm.model = "gpt-4o"
        team = NexusTeam(config)

        active_roles = {r.value for r in AgentRole} - NO_LLM_ROLES
        for role in active_roles:
            assert role in team._agent_llms, f"Role {role} missing for openai provider"
