"""GitNexus code intelligence tool — indexes repos into knowledge graphs for token-efficient analysis.

Wraps the GitNexus CLI (https://github.com/abhigyanpatwari/GitNexus) to provide:
- Semantic code search via knowledge graphs
- Symbol context (callers, callees, execution flows)
- Blast radius / impact analysis before edits
- Git-diff change detection mapped to affected processes
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Any

from nexus.core.tool import Tool, ToolParam, ToolResult, ToolStatus

logger = logging.getLogger(__name__)

_GITNEXUS_TIMEOUT = 120


def _gitnexus_bin() -> str | None:
    """Return the path to the gitnexus binary, or None if not installed."""
    return shutil.which("gitnexus") or shutil.which("npx")


def _run_gitnexus(args: list[str], cwd: str | None = None) -> ToolResult:
    """Run a gitnexus CLI command and return a ToolResult."""
    binary = shutil.which("gitnexus")
    if binary:
        cmd = [binary, *args]
    elif shutil.which("npx"):
        cmd = ["npx", "-y", "gitnexus@latest", *args]
    else:
        return ToolResult(
            status=ToolStatus.ERROR,
            error="gitnexus is not installed. Run: npm install -g gitnexus",
        )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_GITNEXUS_TIMEOUT,
            cwd=cwd,
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Command failed"
            if output:
                return ToolResult(
                    status=ToolStatus.SUCCESS,
                    output=output,
                    metadata={"stderr": error_msg},
                )
            return ToolResult(status=ToolStatus.ERROR, error=error_msg)

        return ToolResult(
            status=ToolStatus.SUCCESS,
            output=output,
            metadata={"command": " ".join(args)},
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            status=ToolStatus.TIMEOUT,
            error=f"gitnexus command timed out after {_GITNEXUS_TIMEOUT}s",
        )
    except Exception as e:
        return ToolResult(status=ToolStatus.ERROR, error=str(e))


class GitNexusAnalyzeTool(Tool):
    """Index a repository into a GitNexus knowledge graph."""

    name = "gitnexus_analyze"
    description = (
        "Index a codebase into a knowledge graph for efficient code intelligence. "
        "Run this before using query/context/impact tools on a new repo."
    )
    parameters = [
        ToolParam(
            name="path",
            type="string",
            description="Path to the repository to index",
            required=False,
            default=".",
        ),
        ToolParam(
            name="force",
            type="boolean",
            description="Force full re-index (ignore existing index)",
            required=False,
            default=False,
        ),
    ]

    def execute(self, **params: Any) -> ToolResult:
        path = params.get("path", ".")
        force = params.get("force", False)
        args = ["analyze", path]
        if force:
            args.append("--force")
        args.append("--skip-embeddings")
        return _run_gitnexus(args, cwd=path)


class GitNexusQueryTool(Tool):
    """Search the knowledge graph by concept — finds symbols, execution flows, and clusters."""

    name = "gitnexus_query"
    description = (
        "Search the codebase knowledge graph by concept instead of reading entire files. "
        "Returns relevant symbols, execution flows, and functional clusters. "
        "Much more token-efficient than grep for understanding code architecture."
    )
    parameters = [
        ToolParam(
            name="query",
            type="string",
            description="Natural language query (e.g. 'auth validation', 'database connection')",
        ),
        ToolParam(
            name="repo",
            type="string",
            description="Repository name (optional if only one repo is indexed)",
            required=False,
            default="",
        ),
    ]

    def execute(self, **params: Any) -> ToolResult:
        query = params["query"]
        repo = params.get("repo", "")
        args = ["query", query]
        if repo:
            args.extend(["--repo", repo])
        return _run_gitnexus(args)


class GitNexusContextTool(Tool):
    """Get 360-degree view of a symbol — callers, callees, process participation."""

    name = "gitnexus_context"
    description = (
        "Get full context for a specific symbol: who calls it, what it calls, "
        "which execution flows it participates in, and its cluster membership. "
        "Use instead of reading multiple files to understand a symbol's role."
    )
    parameters = [
        ToolParam(
            name="name",
            type="string",
            description="Symbol name (function, class, method) to get context for",
        ),
        ToolParam(
            name="repo",
            type="string",
            description="Repository name (optional if only one repo is indexed)",
            required=False,
            default="",
        ),
    ]

    def execute(self, **params: Any) -> ToolResult:
        name = params["name"]
        repo = params.get("repo", "")
        args = ["context", name]
        if repo:
            args.extend(["--repo", repo])
        return _run_gitnexus(args)


class GitNexusImpactTool(Tool):
    """Analyze blast radius before editing a symbol."""

    name = "gitnexus_impact"
    description = (
        "Analyze the blast radius of changing a symbol — shows all upstream/downstream "
        "dependents that could be affected. Run BEFORE editing code to understand risk. "
        "Returns risk level (LOW/MEDIUM/HIGH/CRITICAL) and affected execution flows."
    )
    parameters = [
        ToolParam(
            name="target",
            type="string",
            description="Symbol name to analyze impact for",
        ),
        ToolParam(
            name="direction",
            type="string",
            description="Impact direction: 'upstream' (callers) or 'downstream' (callees)",
            required=False,
            default="upstream",
        ),
        ToolParam(
            name="repo",
            type="string",
            description="Repository name (optional if only one repo is indexed)",
            required=False,
            default="",
        ),
    ]

    def execute(self, **params: Any) -> ToolResult:
        target = params["target"]
        direction = params.get("direction", "upstream")
        repo = params.get("repo", "")
        args = ["impact", target, "--direction", direction]
        if repo:
            args.extend(["--repo", repo])
        return _run_gitnexus(args)


class GitNexusDetectChangesTool(Tool):
    """Map git changes to affected symbols and execution flows."""

    name = "gitnexus_detect_changes"
    description = (
        "Detect which symbols and execution flows are affected by current git changes. "
        "Use before committing to verify only expected code is impacted."
    )
    parameters = [
        ToolParam(
            name="scope",
            type="string",
            description="Scope of changes: 'staged', 'all', or 'compare'",
            required=False,
            default="staged",
        ),
        ToolParam(
            name="base_ref",
            type="string",
            description="Base ref for compare scope (e.g. 'main')",
            required=False,
            default="",
        ),
    ]

    def execute(self, **params: Any) -> ToolResult:
        scope = params.get("scope", "staged")
        base_ref = params.get("base_ref", "")
        args = ["detect-changes", "--scope", scope]
        if base_ref and scope == "compare":
            args.extend(["--base-ref", base_ref])
        return _run_gitnexus(args)


class GitNexusStatusTool(Tool):
    """Check the index status for the current repository."""

    name = "gitnexus_status"
    description = "Show the knowledge graph index status: freshness, symbol count, and staleness."
    parameters = [
        ToolParam(
            name="path",
            type="string",
            description="Path to the repository",
            required=False,
            default=".",
        ),
    ]

    def execute(self, **params: Any) -> ToolResult:
        path = params.get("path", ".")
        return _run_gitnexus(["status"], cwd=path)


class GitNexusListTool(Tool):
    """List all indexed repositories."""

    name = "gitnexus_list"
    description = "List all repositories that have been indexed by GitNexus."
    parameters: list[ToolParam] = []

    def execute(self, **params: Any) -> ToolResult:
        return _run_gitnexus(["list"])


def is_gitnexus_available() -> bool:
    """Check whether the gitnexus CLI is available."""
    return _gitnexus_bin() is not None


GITNEXUS_TOOLS: list[Tool] = [
    GitNexusAnalyzeTool(),
    GitNexusQueryTool(),
    GitNexusContextTool(),
    GitNexusImpactTool(),
    GitNexusDetectChangesTool(),
    GitNexusStatusTool(),
    GitNexusListTool(),
]
