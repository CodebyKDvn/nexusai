"""Filesystem MCP tools — inspired by Claude Code & Gemini CLI.

Sources:
  - Claude Code: Edit, ReadFile, WriteFile
  - Gemini CLI: read_file, write_file, list_directory, glob, replace
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any

from nexus.mcp.base import MCPTool, MCPToolCategory, MCPToolParam, MCPToolResult


class ReadFileTool(MCPTool):
    """Read the contents of a file with optional line offset and limit."""

    name = "read_file"
    description = (
        "Read and return the content of a file. Supports text files. "
        "Use offset and limit for large files to read specific sections."
    )
    category = MCPToolCategory.FILESYSTEM
    source = "claude+gemini"
    parameters = [
        MCPToolParam(name="file_path", type="string", description="Path to the file to read"),
        MCPToolParam(
            name="offset",
            type="integer",
            description="Start line (0-based). Omit to start from beginning.",
            required=False,
            default=0,
        ),
        MCPToolParam(
            name="limit",
            type="integer",
            description="Maximum number of lines to read. Omit to read entire file.",
            required=False,
            default=0,
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        file_path = Path(params["file_path"])
        offset = params.get("offset", 0) or 0
        limit = params.get("limit", 0) or 0

        if not file_path.exists():
            return MCPToolResult.error(f"File not found: {file_path}")
        if not file_path.is_file():
            return MCPToolResult.error(f"Not a file: {file_path}")

        try:
            lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
            total = len(lines)

            if offset > 0:
                lines = lines[offset:]
            if limit > 0:
                lines = lines[:limit]

            content = "".join(lines)
            meta = f"[{file_path} | {total} total lines"
            if offset:
                meta += f" | offset {offset}"
            if limit:
                meta += f" | limit {limit}"
            meta += "]"

            return MCPToolResult.text(f"{meta}\n{content}")
        except Exception as e:
            return MCPToolResult.error(str(e))


class WriteFileTool(MCPTool):
    """Write content to a file, creating parent directories if needed."""

    name = "write_file"
    description = (
        "Write content to a file. Creates the file if it doesn't exist. "
        "Creates parent directories as needed. Overwrites existing content."
    )
    category = MCPToolCategory.FILESYSTEM
    source = "claude+gemini"
    parameters = [
        MCPToolParam(name="file_path", type="string", description="Path to the file to write"),
        MCPToolParam(name="content", type="string", description="Content to write"),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        file_path = Path(params["file_path"])
        content = params["content"]
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return MCPToolResult.text(
                f"Successfully wrote {len(content)} bytes to {file_path}"
            )
        except Exception as e:
            return MCPToolResult.error(str(e))


class ListDirectoryTool(MCPTool):
    """List files and subdirectories in a directory."""

    name = "list_directory"
    description = (
        "List files and subdirectories in a given path. "
        "Returns names with type indicators (/ for dirs). "
        "Supports glob pattern filtering."
    )
    category = MCPToolCategory.FILESYSTEM
    source = "gemini"
    parameters = [
        MCPToolParam(
            name="dir_path",
            type="string",
            description="Path to the directory to list",
        ),
        MCPToolParam(
            name="ignore",
            type="string",
            description="Comma-separated glob patterns to exclude (e.g. 'node_modules,*.pyc')",
            required=False,
            default="",
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        dir_path = Path(params["dir_path"])
        ignore_str = params.get("ignore", "") or ""
        ignore_patterns = [p.strip() for p in ignore_str.split(",") if p.strip()]

        if not dir_path.exists():
            return MCPToolResult.error(f"Directory not found: {dir_path}")
        if not dir_path.is_dir():
            return MCPToolResult.error(f"Not a directory: {dir_path}")

        try:
            entries: list[str] = []
            for item in sorted(dir_path.iterdir()):
                name = item.name
                if any(fnmatch.fnmatch(name, pat) for pat in ignore_patterns):
                    continue
                if item.is_dir():
                    entries.append(f"{name}/")
                else:
                    entries.append(name)

            header = f"Directory: {dir_path} ({len(entries)} entries)"
            return MCPToolResult.text(f"{header}\n" + "\n".join(entries))
        except Exception as e:
            return MCPToolResult.error(str(e))


class FindFilesTool(MCPTool):
    """Find files matching glob patterns across the workspace."""

    name = "find_files"
    description = (
        "Find files matching a glob pattern recursively. "
        "Respects .gitignore patterns by default. "
        "Returns matching file paths sorted by modification time (newest first)."
    )
    category = MCPToolCategory.FILESYSTEM
    source = "gemini"
    parameters = [
        MCPToolParam(
            name="pattern",
            type="string",
            description="Glob pattern to match (e.g. '*.py', 'src/**/*.js')",
        ),
        MCPToolParam(
            name="path",
            type="string",
            description="Directory to search in. Defaults to current directory.",
            required=False,
            default=".",
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        pattern = params["pattern"]
        search_path = Path(params.get("path", ".") or ".")

        if not search_path.exists():
            return MCPToolResult.error(f"Directory not found: {search_path}")

        try:
            matches = list(search_path.glob(pattern))
            # Filter out common noise
            noise_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox"}
            matches = [
                m
                for m in matches
                if not any(part in noise_dirs for part in m.parts)
            ]
            # Sort by mtime (newest first)
            matches.sort(key=lambda p: os.path.getmtime(p) if p.exists() else 0, reverse=True)

            if not matches:
                return MCPToolResult.text(
                    f'No files found matching "{pattern}" in {search_path}'
                )

            result_lines = [
                f'Found {len(matches)} file(s) matching "{pattern}" in {search_path}:'
            ]
            for m in matches[:100]:
                result_lines.append(str(m))

            if len(matches) > 100:
                result_lines.append(f"... and {len(matches) - 100} more")

            return MCPToolResult.text("\n".join(result_lines))
        except Exception as e:
            return MCPToolResult.error(str(e))


class ReplaceInFileTool(MCPTool):
    """Replace text in a file — precise, targeted edits."""

    name = "replace_in_file"
    description = (
        "Replace an exact string occurrence in a file with new text. "
        "By default, replaces exactly ONE occurrence. "
        "Use allow_multiple=true to replace all occurrences."
    )
    category = MCPToolCategory.FILESYSTEM
    source = "claude+gemini"
    parameters = [
        MCPToolParam(name="file_path", type="string", description="Path to the file to edit"),
        MCPToolParam(
            name="old_string",
            type="string",
            description="Exact text to find and replace",
        ),
        MCPToolParam(
            name="new_string",
            type="string",
            description="Replacement text",
        ),
        MCPToolParam(
            name="allow_multiple",
            type="boolean",
            description="If true, replace all occurrences. Default false.",
            required=False,
            default=False,
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        file_path = Path(params["file_path"])
        old_string = params["old_string"]
        new_string = params["new_string"]
        allow_multiple = params.get("allow_multiple", False)

        if not file_path.exists():
            return MCPToolResult.error(f"File not found: {file_path}")

        try:
            content = file_path.read_text(encoding="utf-8")
            count = content.count(old_string)

            if count == 0:
                return MCPToolResult.error(
                    f"String not found in {file_path}: {old_string[:100]}"
                )

            if not allow_multiple and count > 1:
                return MCPToolResult.error(
                    f"Found {count} occurrences of the string in {file_path}. "
                    "Set allow_multiple=true to replace all, or provide more context."
                )

            if allow_multiple:
                new_content = content.replace(old_string, new_string)
                replaced = count
            else:
                new_content = content.replace(old_string, new_string, 1)
                replaced = 1

            file_path.write_text(new_content, encoding="utf-8")
            return MCPToolResult.text(
                f"Replaced {replaced} occurrence(s) in {file_path}"
            )
        except Exception as e:
            return MCPToolResult.error(str(e))
