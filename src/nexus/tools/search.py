"""Code search tools."""

from __future__ import annotations

import subprocess
from typing import Any

from nexus.core.tool import Tool, ToolParam, ToolResult, ToolStatus


class GrepTool(Tool):
    name = "grep"
    description = "Search for a pattern in files using ripgrep."
    parameters = [
        ToolParam(name="pattern", type="string", description="Regex pattern to search for"),
        ToolParam(
            name="path",
            type="string",
            description="Directory or file to search in",
            required=False,
            default=".",
        ),
        ToolParam(
            name="glob",
            type="string",
            description="Glob pattern to filter files (e.g. '*.py')",
            required=False,
            default="",
        ),
        ToolParam(
            name="case_insensitive",
            type="boolean",
            description="Case-insensitive search",
            required=False,
            default=False,
        ),
    ]

    def execute(self, **params: Any) -> ToolResult:
        pattern = params["pattern"]
        path = params.get("path", ".")
        glob = params.get("glob", "")
        case_insensitive = params.get("case_insensitive", False)

        args = ["rg", "--line-number", "--max-count", "100"]
        if case_insensitive:
            args.append("-i")
        if glob:
            args.extend(["--glob", glob])
        args.extend([pattern, path])

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=15,
            )
            output = result.stdout.strip()
            if not output and result.returncode == 1:
                return ToolResult(
                    status=ToolStatus.SUCCESS,
                    output="No matches found.",
                    metadata={"pattern": pattern, "path": path, "matches": 0},
                )

            lines = output.split("\n")
            return ToolResult(
                status=ToolStatus.SUCCESS,
                output=output,
                metadata={"pattern": pattern, "path": path, "matches": len(lines)},
            )
        except FileNotFoundError:
            try:
                args_grep = ["grep", "-rn"]
                if case_insensitive:
                    args_grep.append("-i")
                args_grep.extend([pattern, path])
                result = subprocess.run(
                    args_grep,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                return ToolResult(
                    status=ToolStatus.SUCCESS,
                    output=result.stdout.strip() or "No matches found.",
                )
            except Exception as e:
                return ToolResult(status=ToolStatus.ERROR, error=str(e))
        except Exception as e:
            return ToolResult(status=ToolStatus.ERROR, error=str(e))
