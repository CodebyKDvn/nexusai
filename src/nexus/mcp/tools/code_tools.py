"""Code intelligence MCP tools — inspired by Codex & Claude Code.

Sources:
  - Codex: Code transformation, refactoring, modernization
  - Claude Code: Code understanding, review
  - All LLM reasoning routed through NVIDIA NIM via NvidiaToolWrapper
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from nexus.mcp.base import MCPTool, MCPToolCategory, MCPToolParam, MCPToolResult
from nexus.mcp.nvidia_wrapper import NvidiaToolWrapper


def _get_wrapper() -> NvidiaToolWrapper:
    """Get a NvidiaToolWrapper instance using environment API key."""
    return NvidiaToolWrapper(api_key=os.environ.get("NVIDIA_API_KEY", ""))


class CodeRefactorTool(MCPTool):
    """Refactor code using NVIDIA NIM for intelligent transformation."""

    name = "code_refactor"
    description = (
        "Refactor or transform code according to instructions. "
        "Uses NVIDIA NIM for intelligent code transformation. "
        "Supports: renaming, extracting functions, simplifying logic, "
        "modernizing patterns, converting between frameworks, etc. "
        "Requires NVIDIA_API_KEY."
    )
    category = MCPToolCategory.CODE
    source = "codex"
    parameters = [
        MCPToolParam(
            name="file_path",
            type="string",
            description="Path to the file to refactor",
        ),
        MCPToolParam(
            name="instruction",
            type="string",
            description="What refactoring to apply (e.g. 'Extract the validation logic into a separate function')",
        ),
        MCPToolParam(
            name="language",
            type="string",
            description="Programming language. Default: auto-detect from extension.",
            required=False,
            default="",
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        file_path = Path(params["file_path"])
        instruction = params["instruction"]
        language = params.get("language", "") or ""

        if not file_path.exists():
            return MCPToolResult.error(f"File not found: {file_path}")

        if not language:
            ext_map = {
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".java": "java",
                ".rs": "rust",
                ".go": "go",
                ".rb": "ruby",
                ".cpp": "cpp",
                ".c": "c",
                ".cs": "csharp",
            }
            language = ext_map.get(file_path.suffix, "python")

        try:
            code = file_path.read_text(encoding="utf-8")
            wrapper = _get_wrapper()

            if not wrapper.is_configured:
                return MCPToolResult.error(
                    "NVIDIA_API_KEY not set. Code refactoring requires NVIDIA NIM. "
                    "Set the NVIDIA_API_KEY environment variable."
                )

            result = wrapper.code_transform(code, instruction, language)
            file_path.write_text(result, encoding="utf-8")
            return MCPToolResult.text(
                f"Refactored {file_path} ({language}):\n"
                f"Instruction: {instruction}\n"
                f"Written {len(result)} bytes."
            )
        except Exception as e:
            return MCPToolResult.error(f"Refactoring failed: {e}")


class CodeExplainTool(MCPTool):
    """Explain code using NVIDIA NIM."""

    name = "code_explain"
    description = (
        "Explain what a piece of code does. Reads a file (or portion) "
        "and uses NVIDIA NIM to provide a clear, concise explanation. "
        "Requires NVIDIA_API_KEY."
    )
    category = MCPToolCategory.CODE
    source = "codex"
    parameters = [
        MCPToolParam(
            name="file_path",
            type="string",
            description="Path to the file to explain",
        ),
        MCPToolParam(
            name="start_line",
            type="integer",
            description="Start line (1-based). Omit to explain entire file.",
            required=False,
            default=0,
        ),
        MCPToolParam(
            name="end_line",
            type="integer",
            description="End line (1-based). Omit to explain to end of file.",
            required=False,
            default=0,
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        file_path = Path(params["file_path"])
        start = params.get("start_line", 0) or 0
        end = params.get("end_line", 0) or 0

        if not file_path.exists():
            return MCPToolResult.error(f"File not found: {file_path}")

        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
            if start > 0:
                lines = lines[start - 1 :]
            if end > 0 and start > 0:
                lines = lines[: end - start + 1]
            elif end > 0:
                lines = lines[:end]

            code = "\n".join(lines)
            ext_map = {
                ".py": "python", ".js": "javascript", ".ts": "typescript",
                ".java": "java", ".rs": "rust", ".go": "go",
            }
            language = ext_map.get(file_path.suffix, "python")

            wrapper = _get_wrapper()
            if not wrapper.is_configured:
                return MCPToolResult.error(
                    "NVIDIA_API_KEY not set. Code explanation requires NVIDIA NIM."
                )

            explanation = wrapper.explain_code(code, language)
            header = f"Explanation of {file_path}"
            if start:
                header += f" (lines {start}-{end or 'end'})"
            return MCPToolResult.text(f"{header}:\n\n{explanation}")
        except Exception as e:
            return MCPToolResult.error(f"Explanation failed: {e}")


class CodeReviewTool(MCPTool):
    """Review code quality using NVIDIA NIM."""

    name = "code_review"
    description = (
        "Review code for quality, bugs, security issues, and improvements. "
        "Uses NVIDIA NIM to analyze code and provide structured feedback. "
        "Requires NVIDIA_API_KEY."
    )
    category = MCPToolCategory.CODE
    source = "codex"
    parameters = [
        MCPToolParam(
            name="file_path",
            type="string",
            description="Path to the file to review",
        ),
        MCPToolParam(
            name="focus",
            type="string",
            description="Focus area: 'bugs', 'security', 'performance', 'style', or 'all'",
            required=False,
            default="all",
            enum=["bugs", "security", "performance", "style", "all"],
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        file_path = Path(params["file_path"])
        focus = params.get("focus", "all") or "all"

        if not file_path.exists():
            return MCPToolResult.error(f"File not found: {file_path}")

        try:
            code = file_path.read_text(encoding="utf-8")
            wrapper = _get_wrapper()

            if not wrapper.is_configured:
                return MCPToolResult.error(
                    "NVIDIA_API_KEY not set. Code review requires NVIDIA NIM."
                )

            system_prompt = (
                "You are a senior code reviewer. Review the given code and provide "
                "structured feedback as JSON with fields: "
                "'issues' (list of {severity, line, description}), "
                "'suggestions' (list of strings), "
                "'overall_quality' (1-10), "
                "'summary' (one paragraph)."
            )
            if focus != "all":
                system_prompt += f" Focus specifically on {focus} issues."

            result = wrapper.reason_json(
                system_prompt,
                f"File: {file_path}\n\n```\n{code}\n```",
            )
            return MCPToolResult.json_result(result)
        except Exception as e:
            return MCPToolResult.error(f"Code review failed: {e}")


class SuggestFixTool(MCPTool):
    """Suggest fixes for code errors using NVIDIA NIM."""

    name = "suggest_fix"
    description = (
        "Given code that produces an error, suggest a fix. "
        "Reads the file, analyzes the error message, and uses NVIDIA NIM "
        "to generate corrected code. Requires NVIDIA_API_KEY."
    )
    category = MCPToolCategory.CODE
    source = "codex"
    parameters = [
        MCPToolParam(
            name="file_path",
            type="string",
            description="Path to the file with the error",
        ),
        MCPToolParam(
            name="error_message",
            type="string",
            description="The error message or traceback",
        ),
        MCPToolParam(
            name="apply",
            type="boolean",
            description="If true, write the fix directly to the file. Default false.",
            required=False,
            default=False,
        ),
    ]

    def execute(self, **params: Any) -> MCPToolResult:
        file_path = Path(params["file_path"])
        error_message = params["error_message"]
        apply = params.get("apply", False)

        if not file_path.exists():
            return MCPToolResult.error(f"File not found: {file_path}")

        try:
            code = file_path.read_text(encoding="utf-8")
            ext_map = {
                ".py": "python", ".js": "javascript", ".ts": "typescript",
                ".java": "java", ".rs": "rust", ".go": "go",
            }
            language = ext_map.get(file_path.suffix, "python")

            wrapper = _get_wrapper()
            if not wrapper.is_configured:
                return MCPToolResult.error(
                    "NVIDIA_API_KEY not set. Fix suggestion requires NVIDIA NIM."
                )

            fixed_code = wrapper.suggest_fix(code, error_message, language)

            if apply:
                file_path.write_text(fixed_code, encoding="utf-8")
                return MCPToolResult.text(
                    f"Fix applied to {file_path}. Written {len(fixed_code)} bytes."
                )
            return MCPToolResult.text(
                f"Suggested fix for {file_path}:\n\n{fixed_code}"
            )
        except Exception as e:
            return MCPToolResult.error(f"Fix suggestion failed: {e}")
