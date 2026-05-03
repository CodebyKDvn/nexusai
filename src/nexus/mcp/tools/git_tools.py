"""Git MCP tools — inspired by Claude Code & Codex.

Sources:
  - Claude Code: Git operations (status, diff, commit, log)
  - Codex: Git integration for code management
"""

from __future__ import annotations

import subprocess
from typing import Any

from nexus.mcp.base import MCPTool, MCPToolCategory, MCPToolParam, MCPToolResult


def _run_git(args: list[str], cwd: str = ".") -> MCPToolResult:
    """Run a git command and return an MCPToolResult."""
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

        if result.returncode != 0:
            return MCPToolResult.error(output or f"git {' '.join(args)} failed")

        return MCPToolResult.text(output or "(no output)")
    except Exception as e:
        return MCPToolResult.error(f"git error: {e}")


class GitStatusMCPTool(MCPTool):
    """Show the working tree status."""

    name = "git_status"
    description = (
        "Show the git working tree status — modified, staged, and untracked files. "
        "Equivalent to 'git status --short'."
    )
    category = MCPToolCategory.GIT
    source = "claude"
    parameters = [
        MCPToolParam(
            name="cwd",
            type="string",
            description="Repository directory",
            required=False,
            default=".",
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        return _run_git(["status", "--short"], cwd=params.get("cwd", ".") or ".")


class GitDiffMCPTool(MCPTool):
    """Show changes in the working directory or between commits."""

    name = "git_diff"
    description = (
        "Show git diff — changes in the working directory, staged changes, "
        "or differences between commits/branches."
    )
    category = MCPToolCategory.GIT
    source = "claude"
    parameters = [
        MCPToolParam(
            name="ref",
            type="string",
            description="Git ref to diff against (e.g. HEAD, branch name, commit SHA)",
            required=False,
            default="",
        ),
        MCPToolParam(
            name="staged",
            type="boolean",
            description="Show staged changes only (--cached). Default false.",
            required=False,
            default=False,
        ),
        MCPToolParam(
            name="cwd",
            type="string",
            description="Repository directory",
            required=False,
            default=".",
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        args = ["diff"]
        if params.get("staged"):
            args.append("--cached")
        ref = params.get("ref", "") or ""
        if ref:
            args.append(ref)
        return _run_git(args, cwd=params.get("cwd", ".") or ".")


class GitLogTool(MCPTool):
    """Show commit history."""

    name = "git_log"
    description = (
        "Show git commit history with hash, author, date, and message. "
        "Useful for understanding recent changes and finding specific commits."
    )
    category = MCPToolCategory.GIT
    source = "claude+codex"
    parameters = [
        MCPToolParam(
            name="max_count",
            type="integer",
            description="Maximum number of commits to show. Default 20.",
            required=False,
            default=20,
        ),
        MCPToolParam(
            name="oneline",
            type="boolean",
            description="One-line format. Default true.",
            required=False,
            default=True,
        ),
        MCPToolParam(
            name="path",
            type="string",
            description="Filter to commits touching this file/directory",
            required=False,
            default="",
        ),
        MCPToolParam(
            name="cwd",
            type="string",
            description="Repository directory",
            required=False,
            default=".",
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        max_count = params.get("max_count", 20) or 20
        oneline = params.get("oneline", True)
        filter_path = params.get("path", "") or ""

        args = ["log", f"--max-count={max_count}"]
        if oneline:
            args.append("--oneline")
        else:
            args.extend(["--format=%H %an %ad %s", "--date=short"])

        if filter_path:
            args.extend(["--", filter_path])

        return _run_git(args, cwd=params.get("cwd", ".") or ".")


class GitCommitMCPTool(MCPTool):
    """Stage and commit changes."""

    name = "git_commit"
    description = (
        "Stage specified files (or all changes) and create a git commit. "
        "Always creates a new commit — never amends."
    )
    category = MCPToolCategory.GIT
    source = "claude+codex"
    parameters = [
        MCPToolParam(
            name="message",
            type="string",
            description="Commit message",
        ),
        MCPToolParam(
            name="files",
            type="string",
            description="Space-separated file paths to stage. Use '.' for all.",
            required=False,
            default=".",
        ),
        MCPToolParam(
            name="cwd",
            type="string",
            description="Repository directory",
            required=False,
            default=".",
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        cwd = params.get("cwd", ".") or "."
        files = params.get("files", ".") or "."
        message = params["message"]

        file_list = files.split() if files != "." else ["-A"]
        add_result = _run_git(["add"] + file_list, cwd=cwd)
        if add_result.is_error:
            return add_result

        return _run_git(["commit", "-m", message], cwd=cwd)
