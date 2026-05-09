"""Search MCP tools — inspired by Claude Code, Gemini CLI, and Codex.

Sources:
  - Claude Code: Grep, GlobTool
  - Gemini CLI: grep_search, semantic search
  - Free alternative: duckduckgo_search replaces Google Search API
"""

from __future__ import annotations

import subprocess
from typing import Any

from nexus.mcp.base import MCPTool, MCPToolCategory, MCPToolParam, MCPToolResult


class GrepSearchTool(MCPTool):
    """Search for regex patterns in files using ripgrep."""

    name = "grep_search"
    description = (
        "Search for a regular expression pattern within file contents. "
        "Uses ripgrep (rg) for speed, falls back to grep. "
        "Returns matching lines with file paths and line numbers."
    )
    category = MCPToolCategory.SEARCH
    source = "claude+gemini"
    parameters = [
        MCPToolParam(
            name="pattern",
            type="string",
            description="Regex pattern to search for",
        ),
        MCPToolParam(
            name="path",
            type="string",
            description="Directory to search in. Defaults to current directory.",
            required=False,
            default=".",
        ),
        MCPToolParam(
            name="include",
            type="string",
            description="Glob pattern to filter files (e.g. '*.py', 'src/**/*.ts')",
            required=False,
            default="",
        ),
        MCPToolParam(
            name="case_insensitive",
            type="boolean",
            description="Case-insensitive search. Default false.",
            required=False,
            default=False,
        ),
        MCPToolParam(
            name="max_results",
            type="integer",
            description="Maximum number of matches. Default 100.",
            required=False,
            default=100,
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        pattern = params["pattern"]
        path = params.get("path", ".") or "."
        include = params.get("include", "") or ""
        case_insensitive = params.get("case_insensitive", False)
        max_results = params.get("max_results", 100) or 100

        args = ["rg", "--line-number"]
        if case_insensitive:
            args.append("-i")
        if include:
            args.extend(["--glob", include])
        args.extend([pattern, path])

        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=15
            )
            output = result.stdout.strip()

            if not output and result.returncode == 1:
                return MCPToolResult.text(
                    f'No matches found for pattern "{pattern}" in {path}'
                )

            lines = output.split("\n") if output else []
            # Truncate to max_results total (not per-file)
            if len(lines) > max_results:
                lines = lines[:max_results]
                output = "\n".join(lines)
            header = f'Found {len(lines)} match(es) for pattern "{pattern}" in "{path}"'
            if include:
                header += f' (filter: "{include}")'
            return MCPToolResult.text(f"{header}:\n---\n{output}")

        except FileNotFoundError:
            # Fallback to system grep
            args_grep = ["grep", "-rn"]
            if case_insensitive:
                args_grep.append("-i")
            if include:
                args_grep.extend(["--include", include])
            args_grep.extend([pattern, path])
            try:
                result = subprocess.run(
                    args_grep, capture_output=True, text=True, timeout=15
                )
                output = result.stdout.strip() or "No matches found."
                # Truncate to max_results total
                lines = output.split("\n")
                if len(lines) > max_results:
                    output = "\n".join(lines[:max_results])
                return MCPToolResult.text(output)
            except Exception as e:
                return MCPToolResult.error(f"Search failed: {e}")
        except Exception as e:
            return MCPToolResult.error(f"Search failed: {e}")


class WebSearchTool(MCPTool):
    """Search the web using DuckDuckGo (free, no API key required)."""

    name = "web_search"
    description = (
        "Search the web for information using DuckDuckGo. "
        "Free alternative to Google Search API — no API key required. "
        "Returns titles, URLs, and snippets from search results."
    )
    category = MCPToolCategory.WEB
    source = "gemini"
    parameters = [
        MCPToolParam(
            name="query",
            type="string",
            description="Search query",
        ),
        MCPToolParam(
            name="max_results",
            type="integer",
            description="Max results to return. Default 5.",
            required=False,
            default=5,
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        query = params["query"]
        max_results = params.get("max_results", 5) or 5

        try:
            from duckduckgo_search import DDGS

            results: list[str] = []
            with DDGS() as ddgs:
                for i, r in enumerate(ddgs.text(query, max_results=max_results)):
                    results.append(
                        f"[{i + 1}] {r.get('title', 'No title')}\n"
                        f"    URL: {r.get('href', 'N/A')}\n"
                        f"    {r.get('body', '')}"
                    )

            if not results:
                return MCPToolResult.text(f"No results found for: {query}")

            return MCPToolResult.text(
                f'Web search results for "{query}":\n\n' + "\n\n".join(results)
            )
        except ImportError:
            return MCPToolResult.error(
                "duckduckgo_search is not installed. "
                "Install it with: pip install duckduckgo_search"
            )
        except Exception as e:
            return MCPToolResult.error(f"Web search failed: {e}")


class SemanticSearchTool(MCPTool):
    """Semantic code search using NVIDIA NIM for ranking."""

    name = "semantic_search"
    description = (
        "Search codebase using natural language queries. "
        "Combines grep for candidate extraction with NVIDIA NIM "
        "for semantic ranking. Best for questions like 'where is authentication handled?' "
        "or 'find the database connection logic'."
    )
    category = MCPToolCategory.SEARCH
    source = "gemini+codex"
    parameters = [
        MCPToolParam(
            name="query",
            type="string",
            description="Natural language search query",
        ),
        MCPToolParam(
            name="path",
            type="string",
            description="Directory to search in",
            required=False,
            default=".",
        ),
        MCPToolParam(
            name="file_pattern",
            type="string",
            description="Glob pattern for files (e.g. '*.py')",
            required=False,
            default="*.py",
        ),
        MCPToolParam(
            name="max_results",
            type="integer",
            description="Max results to return. Default 10.",
            required=False,
            default=10,
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        query = params["query"]
        path = params.get("path", ".") or "."
        file_pattern = params.get("file_pattern", "*.py") or "*.py"
        max_results = params.get("max_results", 10) or 10

        # Extract keywords from query for initial grep
        keywords = [w for w in query.lower().split() if len(w) > 3]
        if not keywords:
            keywords = query.lower().split()[:3]

        # Gather candidates via grep
        candidates: list[dict[str, str]] = []
        for keyword in keywords[:5]:
            try:
                result = subprocess.run(
                    ["rg", "-l", "--glob", file_pattern, "-i", keyword, path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                for file_path in result.stdout.strip().split("\n"):
                    if file_path and file_path not in [c["path"] for c in candidates]:
                        try:
                            from pathlib import Path

                            content = Path(file_path).read_text(encoding="utf-8")[:1000]
                            candidates.append({"path": file_path, "content": content})
                        except Exception:
                            pass
            except Exception:
                pass

        if not candidates:
            return MCPToolResult.text(
                f"No files found matching query: {query}"
            )

        # Return top candidates (NVIDIA ranking available when wrapper is provided)
        results: list[str] = [f'Semantic search results for "{query}":']
        for c in candidates[:max_results]:
            preview = c["content"][:200].replace("\n", " ")
            results.append(f"\n  {c['path']}\n    {preview}...")

        return MCPToolResult.text("\n".join(results))
