"""Git operation tools."""

from __future__ import annotations

import subprocess
from typing import Any

from nexus.core.tool import Tool, ToolParam, ToolResult, ToolStatus


def _run_git(args: list[str], cwd: str = ".") -> ToolResult:
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30,
        )
        output = result.stdout.strip()
        if result.stderr.strip():
            output += f"\n{result.stderr.strip()}"
        return ToolResult(
            status=ToolStatus.SUCCESS if result.returncode == 0 else ToolStatus.ERROR,
            output=output,
            error=f"Exit code: {result.returncode}" if result.returncode != 0 else None,
            metadata={"command": f"git {' '.join(args)}", "cwd": cwd},
        )
    except Exception as e:
        return ToolResult(status=ToolStatus.ERROR, error=str(e))


class GitStatusTool(Tool):
    name = "git_status"
    description = "Show the working tree status."
    parameters = [
        ToolParam(
            name="cwd",
            type="string",
            description="Repository directory",
            required=False,
            default=".",
        ),
    ]

    def execute(self, **params: Any) -> ToolResult:
        return _run_git(["status", "--short"], cwd=params.get("cwd", "."))


class GitDiffTool(Tool):
    name = "git_diff"
    description = "Show changes in the working directory or between commits."
    parameters = [
        ToolParam(
            name="ref",
            type="string",
            description="Git ref to diff against (e.g. HEAD, branch name)",
            required=False,
            default="",
        ),
        ToolParam(
            name="cwd",
            type="string",
            description="Repository directory",
            required=False,
            default=".",
        ),
    ]

    def execute(self, **params: Any) -> ToolResult:
        args = ["diff"]
        ref = params.get("ref", "")
        if ref:
            args.append(ref)
        return _run_git(args, cwd=params.get("cwd", "."))


class GitCommitTool(Tool):
    name = "git_commit"
    description = "Stage all changes and create a commit."
    parameters = [
        ToolParam(name="message", type="string", description="Commit message"),
        ToolParam(
            name="cwd",
            type="string",
            description="Repository directory",
            required=False,
            default=".",
        ),
    ]

    def execute(self, **params: Any) -> ToolResult:
        cwd = params.get("cwd", ".")
        add_result = _run_git(["add", "-A"], cwd=cwd)
        if not add_result.ok:
            return add_result
        return _run_git(["commit", "-m", params["message"]], cwd=cwd)
