"""Terminal execution tool — runs shell commands in a sandbox."""

from __future__ import annotations

import subprocess
from typing import Any

from nexus.core.tool import Tool, ToolParam, ToolResult, ToolStatus


class TerminalTool(Tool):
    name = "terminal"
    description = "Execute a shell command and capture output."
    parameters = [
        ToolParam(name="command", type="string", description="Shell command to execute"),
        ToolParam(
            name="cwd",
            type="string",
            description="Working directory",
            required=False,
            default=".",
        ),
        ToolParam(
            name="timeout",
            type="integer",
            description="Timeout in seconds",
            required=False,
            default=30,
        ),
    ]

    def execute(self, **params: Any) -> ToolResult:
        command = params["command"]
        cwd = params.get("cwd", ".")
        timeout = params.get("timeout", 30)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
            )
            output = result.stdout
            if result.stderr:
                output += f"\n--- stderr ---\n{result.stderr}"

            max_size = 10000
            if len(output) > max_size:
                output = output[:max_size] + f"\n... (truncated, {len(output)} total chars)"

            return ToolResult(
                status=ToolStatus.SUCCESS if result.returncode == 0 else ToolStatus.ERROR,
                output=output,
                error=f"Exit code: {result.returncode}" if result.returncode != 0 else None,
                metadata={
                    "command": command,
                    "exit_code": result.returncode,
                    "cwd": cwd,
                },
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                status=ToolStatus.TIMEOUT,
                error=f"Command timed out after {timeout}s: {command}",
            )
        except Exception as e:
            return ToolResult(status=ToolStatus.ERROR, error=str(e))
