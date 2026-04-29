"""File system operation tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.core.tool import Tool, ToolParam, ToolResult, ToolStatus


class FileReadTool(Tool):
    name = "file_read"
    description = "Read the contents of a file."
    parameters = [
        ToolParam(name="path", type="string", description="Path to the file to read"),
    ]

    def execute(self, **params: Any) -> ToolResult:
        path = Path(params["path"])
        try:
            if not path.exists():
                return ToolResult(status=ToolStatus.ERROR, error=f"File not found: {path}")
            if not path.is_file():
                return ToolResult(status=ToolStatus.ERROR, error=f"Not a file: {path}")
            content = path.read_text(encoding="utf-8")
            return ToolResult(
                status=ToolStatus.SUCCESS,
                output=content,
                metadata={"path": str(path), "size": len(content)},
            )
        except Exception as e:
            return ToolResult(status=ToolStatus.ERROR, error=str(e))


class FileWriteTool(Tool):
    name = "file_write"
    description = "Write content to a file, creating directories if needed."
    parameters = [
        ToolParam(name="path", type="string", description="Path to the file to write"),
        ToolParam(name="content", type="string", description="Content to write to the file"),
    ]

    def execute(self, **params: Any) -> ToolResult:
        path = Path(params["path"])
        content = params["content"]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolResult(
                status=ToolStatus.SUCCESS,
                output=f"Written {len(content)} bytes to {path}",
                metadata={"path": str(path), "size": len(content)},
            )
        except Exception as e:
            return ToolResult(status=ToolStatus.ERROR, error=str(e))


class FileEditTool(Tool):
    name = "file_edit"
    description = "Replace a string in a file with another string."
    parameters = [
        ToolParam(name="path", type="string", description="Path to the file to edit"),
        ToolParam(name="old_string", type="string", description="String to find and replace"),
        ToolParam(name="new_string", type="string", description="Replacement string"),
    ]

    def execute(self, **params: Any) -> ToolResult:
        path = Path(params["path"])
        old_string = params["old_string"]
        new_string = params["new_string"]
        try:
            if not path.exists():
                return ToolResult(status=ToolStatus.ERROR, error=f"File not found: {path}")
            content = path.read_text(encoding="utf-8")
            if old_string not in content:
                return ToolResult(
                    status=ToolStatus.ERROR,
                    error=f"String not found in {path}: {old_string[:100]}",
                )
            new_content = content.replace(old_string, new_string, 1)
            path.write_text(new_content, encoding="utf-8")
            return ToolResult(
                status=ToolStatus.SUCCESS,
                output=f"Edited {path}: replaced 1 occurrence",
                metadata={"path": str(path)},
            )
        except Exception as e:
            return ToolResult(status=ToolStatus.ERROR, error=str(e))


class FileDeleteTool(Tool):
    name = "file_delete"
    description = "Delete a file."
    parameters = [
        ToolParam(name="path", type="string", description="Path to the file to delete"),
    ]

    def execute(self, **params: Any) -> ToolResult:
        path = Path(params["path"])
        try:
            if not path.exists():
                return ToolResult(status=ToolStatus.ERROR, error=f"File not found: {path}")
            path.unlink()
            return ToolResult(
                status=ToolStatus.SUCCESS,
                output=f"Deleted {path}",
                metadata={"path": str(path)},
            )
        except Exception as e:
            return ToolResult(status=ToolStatus.ERROR, error=str(e))
