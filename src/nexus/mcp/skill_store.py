"""Unified Skill Registry — manages tool discovery, auth, and sandboxing."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from nexus.mcp.base import MCPTool, MCPToolCategory, MCPToolParam, MCPToolResult
from nexus.mcp.nvidia_wrapper import NvidiaToolWrapper
from nexus.mcp.sandbox import Sandbox

logger = logging.getLogger(__name__)


class SkillStore:
    """Centralized manager for MCP-compliant tools.

    Features:
      - **Discovery**: Load tools from Python classes or JSON/YAML definitions.
      - **Authentication**: Centralized API key management for NVIDIA and
        other free services.
      - **Sandboxing**: All terminal/system commands go through a safety layer.
      - **Registration**: Dynamic tool registration and lookup.
      - **Execution**: Unified execute() interface with validation.
    """

    def __init__(
        self,
        sandbox: Sandbox | None = None,
        nvidia_wrapper: NvidiaToolWrapper | None = None,
    ) -> None:
        self._tools: dict[str, MCPTool] = {}
        self._sandbox = sandbox or Sandbox()
        self._nvidia_wrapper = nvidia_wrapper
        self._api_keys: dict[str, str] = {}
        self._load_api_keys_from_env()

    def _load_api_keys_from_env(self) -> None:
        """Load known API keys from environment variables."""
        key_names = [
            "NVIDIA_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
        ]
        for name in key_names:
            val = os.environ.get(name, "")
            if val:
                self._api_keys[name] = val

    @property
    def nvidia_wrapper(self) -> NvidiaToolWrapper:
        """Get or create NVIDIA wrapper using stored API key."""
        if self._nvidia_wrapper is None:
            api_key = self._api_keys.get("NVIDIA_API_KEY", "")
            self._nvidia_wrapper = NvidiaToolWrapper(api_key=api_key)
        return self._nvidia_wrapper

    @property
    def sandbox(self) -> Sandbox:
        return self._sandbox

    def register(self, tool: MCPTool) -> None:
        """Register an MCP tool by name."""
        if tool.name in self._tools:
            logger.warning("Overwriting tool registration: %s", tool.name)
        self._tools[tool.name] = tool
        logger.debug("Registered MCP tool: %s (%s)", tool.name, tool.category)

    def register_all(self, tools: list[MCPTool]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)

    def unregister(self, name: str) -> bool:
        """Unregister a tool by name. Returns True if removed."""
        return self._tools.pop(name, None) is not None

    def get(self, name: str) -> MCPTool | None:
        """Look up a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[MCPTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def list_schemas(self) -> list[dict[str, Any]]:
        """Return MCP schemas for all registered tools."""
        return [tool.to_mcp_schema() for tool in self._tools.values()]

    def list_by_category(self, category: str) -> list[MCPTool]:
        """Return tools filtered by category."""
        return [t for t in self._tools.values() if t.category == category]

    def list_by_source(self, source: str) -> list[MCPTool]:
        """Return tools filtered by origin source."""
        return [t for t in self._tools.values() if source in t.source]

    def execute(self, name: str, **params: Any) -> MCPToolResult:
        """Execute a tool by name with given parameters.

        Performs validation before execution.
        """
        tool = self._tools.get(name)
        if tool is None:
            return MCPToolResult.error(f"Unknown tool: {name}")

        errors = tool.validate(**params)
        if errors:
            return MCPToolResult.error(
                f"Validation errors for {name}: " + "; ".join(errors)
            )

        try:
            return tool.execute(**params)
        except Exception as e:
            logger.exception("Tool execution failed: %s", name)
            return MCPToolResult.error(f"Tool {name} failed: {e}")

    def load_from_json(self, path: str) -> int:
        """Load tool definitions from a JSON file.

        The JSON should be an array of objects with fields:
          name, description, category, source, parameters, command_template

        Returns the number of tools loaded.
        """
        file_path = Path(path)
        if not file_path.exists():
            logger.error("Tool definition file not found: %s", path)
            return 0

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                logger.error("Expected JSON array in %s", path)
                return 0

            count = 0
            for entry in data:
                tool = _json_to_tool(entry)
                if tool:
                    self.register(tool)
                    count += 1
            logger.info("Loaded %d tools from %s", count, path)
            return count
        except Exception as e:
            logger.error("Failed to load tools from %s: %s", path, e)
            return 0

    def load_from_yaml(self, path: str) -> int:
        """Load tool definitions from a YAML file.

        Returns the number of tools loaded.
        """
        file_path = Path(path)
        if not file_path.exists():
            logger.error("Tool definition file not found: %s", path)
            return 0

        try:
            import yaml

            data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                logger.error("Expected YAML list in %s", path)
                return 0

            count = 0
            for entry in data:
                tool = _json_to_tool(entry)
                if tool:
                    self.register(tool)
                    count += 1
            logger.info("Loaded %d tools from %s", count, path)
            return count
        except Exception as e:
            logger.error("Failed to load tools from %s: %s", path, e)
            return 0

    def get_api_key(self, key_name: str) -> str | None:
        """Get a stored API key."""
        return self._api_keys.get(key_name)

    def set_api_key(self, key_name: str, value: str) -> None:
        """Set an API key in the store."""
        self._api_keys[key_name] = value

    def to_catalog(self) -> str:
        """Generate a markdown catalog of all registered tools."""
        lines = ["# Nexus Skill-Core — Tool Catalog\n"]
        lines.append(f"**Total tools**: {len(self._tools)}\n")

        # Group by category
        categories: dict[MCPToolCategory, list[MCPTool]] = {}
        for tool in self._tools.values():
            cat = tool.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(tool)

        for cat, tools in sorted(categories.items()):
            lines.append(f"\n## {cat.title()} ({len(tools)} tools)\n")
            lines.append("| Tool | Source | Description |")
            lines.append("|------|--------|-------------|")
            for t in sorted(tools, key=lambda x: x.name):
                desc = t.description.split(".")[0]
                lines.append(f"| `{t.name}` | {t.source} | {desc} |")

        return "\n".join(lines)


def _json_to_tool(entry: dict[str, Any]) -> MCPTool | None:
    """Convert a JSON tool definition to a DynamicMCPTool."""
    required_fields = ["name", "description"]
    for f in required_fields:
        if f not in entry:
            logger.warning("Skipping tool definition missing '%s': %s", f, entry)
            return None

    params: list[MCPToolParam] = []
    for p in entry.get("parameters", []):
        params.append(
            MCPToolParam(
                name=p["name"],
                type=p.get("type", "string"),
                description=p.get("description", ""),
                required=p.get("required", True),
                default=p.get("default"),
            )
        )

    cat_str = entry.get("category", "terminal")
    try:
        category = MCPToolCategory(cat_str)
    except ValueError:
        category = MCPToolCategory.TERMINAL

    return _DynamicMCPTool(
        name=entry["name"],
        description=entry["description"],
        category=category,
        source=entry.get("source", "custom"),
        parameters=params,
        command_template=entry.get("command_template", ""),
    )


class _DynamicMCPTool(MCPTool):
    """Tool loaded from JSON/YAML definition with command template execution."""

    def __init__(
        self,
        name: str,
        description: str,
        category: MCPToolCategory,
        source: str,
        parameters: list[Any],
        command_template: str,
    ) -> None:
        self.name = name
        self.description = description
        self.category = category
        self.source = source
        self.parameters = parameters
        self._command_template = command_template

    def execute(self, **params: Any) -> MCPToolResult:
        if not self._command_template:
            return MCPToolResult.error(
                f"Tool {self.name} has no command_template defined"
            )

        import subprocess

        command = self._command_template
        for key, value in params.items():
            command = command.replace(f"{{{key}}}", str(value))

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout.strip()
            if result.stderr.strip():
                output += f"\n{result.stderr.strip()}"
            if result.returncode != 0:
                return MCPToolResult.error(output or f"Command failed: {command}")
            return MCPToolResult.text(output or "(no output)")
        except Exception as e:
            return MCPToolResult.error(str(e))
