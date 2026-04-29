"""Tests for the team assembly and end-to-end flow."""

from __future__ import annotations

from nexus.config import NexusConfig
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
