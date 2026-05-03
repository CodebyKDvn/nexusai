"""Terminal/Bash MCP tools — inspired by Claude Code & Codex.

Sources:
  - Claude Code: Bash tool
  - Codex: Terminal execution with sandboxing
"""

from __future__ import annotations

from typing import Any

from nexus.mcp.base import MCPTool, MCPToolCategory, MCPToolParam, MCPToolResult
from nexus.mcp.sandbox import Sandbox


class ExecuteBashTool(MCPTool):
    """Execute shell commands in a sandboxed environment."""

    name = "execute_bash"
    description = (
        "Execute a shell command in the user's environment. "
        "Commands run through a safety sandbox that blocks destructive operations. "
        "Use for: running tests, installing packages, checking system state, "
        "building projects, running linters, etc."
    )
    category = MCPToolCategory.TERMINAL
    source = "claude+codex"
    parameters = [
        MCPToolParam(
            name="command",
            type="string",
            description="The shell command to execute",
        ),
        MCPToolParam(
            name="cwd",
            type="string",
            description="Working directory. Defaults to current directory.",
            required=False,
            default=".",
        ),
        MCPToolParam(
            name="timeout",
            type="integer",
            description="Timeout in seconds. Default 30.",
            required=False,
            default=30,
        ),
    ]

    def __init__(self, sandbox: Sandbox | None = None) -> None:
        self._sandbox = sandbox or Sandbox()

    def execute(self, **params: Any) -> MCPToolResult:
        command = params["command"]
        cwd = params.get("cwd", ".") or "."
        timeout = params.get("timeout", 30) or 30

        try:
            result = self._sandbox.execute(command, cwd=cwd, timeout=timeout)
        except Exception as e:
            return MCPToolResult.error(str(e))

        output_parts: list[str] = []
        if result["stdout"]:
            output_parts.append(result["stdout"])
        if result["stderr"]:
            output_parts.append(f"--- stderr ---\n{result['stderr']}")

        output = "\n".join(output_parts) if output_parts else "(no output)"

        if result["timed_out"]:
            return MCPToolResult.error(f"Command timed out after {timeout}s: {command}")

        if result["exit_code"] != 0:
            return MCPToolResult(
                content=[{
                    "type": "text",
                    "text": f"Exit code {result['exit_code']}:\n{output}",
                }],
                is_error=True,
            )

        return MCPToolResult.text(output)
