"""MCP-compliant base classes for Nexus Skill-Core tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MCPToolCategory(StrEnum):
    """Tool origin/category classification."""

    FILESYSTEM = "filesystem"
    TERMINAL = "terminal"
    SEARCH = "search"
    GIT = "git"
    WEB = "web"
    CODE = "code"
    AI = "ai"


@dataclass(frozen=True)
class MCPToolParam:
    """Parameter definition for an MCP tool (JSON Schema compatible)."""

    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: list[str] | None = None

    def to_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum:
            schema["enum"] = self.enum
        if self.default is not None:
            schema["default"] = self.default
        return schema


@dataclass
class MCPToolResult:
    """Standardized result from an MCP tool execution."""

    content: list[dict[str, Any]] = field(default_factory=list)
    is_error: bool = False

    @staticmethod
    def text(text: str) -> MCPToolResult:
        return MCPToolResult(content=[{"type": "text", "text": text}])

    @staticmethod
    def error(message: str) -> MCPToolResult:
        return MCPToolResult(
            content=[{"type": "text", "text": f"Error: {message}"}],
            is_error=True,
        )

    @staticmethod
    def json_result(data: dict[str, Any]) -> MCPToolResult:
        import json

        return MCPToolResult(content=[{"type": "text", "text": json.dumps(data, indent=2)}])


class MCPTool(ABC):
    """Base class for all MCP-compliant tools in Nexus Skill-Core.

    Every tool must define:
      - name:         unique identifier
      - description:  detailed instructions for the Agent on when to use it
      - category:     origin/purpose classification
      - source:       which platform inspired this tool (claude/gemini/codex/nexus)
      - parameters:   list of MCPToolParam defining the input schema
      - execute():    the local execution logic
    """

    name: str
    description: str
    category: MCPToolCategory
    source: str  # "claude" | "gemini" | "codex" | "nexus"
    parameters: list[MCPToolParam]

    @abstractmethod
    def execute(self, **params: Any) -> MCPToolResult:
        """Execute the tool with given parameters."""

    @property
    def input_schema(self) -> dict[str, Any]:
        """Generate JSON Schema for this tool's parameters."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for p in self.parameters:
            properties[p.name] = p.to_schema()
            if p.required:
                required.append(p.name)
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema

    def to_mcp_schema(self) -> dict[str, Any]:
        """Full MCP tool definition for server registration."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

    def validate(self, **params: Any) -> list[str]:
        """Validate parameters against schema, returning error messages."""
        errors: list[str] = []
        for p in self.parameters:
            if p.required and p.name not in params:
                errors.append(f"Missing required parameter: {p.name}")
        return errors
