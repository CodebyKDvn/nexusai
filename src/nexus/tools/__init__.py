"""Built-in tools for Nexus AI agents."""

from nexus.core.tool import Tool, ToolParam, ToolRegistry, ToolResult, ToolStatus
from nexus.tools.api import APITool
from nexus.tools.browser import BrowserTool
from nexus.tools.file_ops import (
    FileDeleteTool,
    FileEditTool,
    FileReadTool,
    FileWriteTool,
)
from nexus.tools.git_ops import GitCommitTool, GitDiffTool, GitStatusTool
from nexus.tools.search import GrepTool
from nexus.tools.terminal import TerminalTool


def create_default_registry() -> ToolRegistry:
    """Create a registry with all default tools."""
    registry = ToolRegistry()
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(FileEditTool())
    registry.register(FileDeleteTool())
    registry.register(TerminalTool())
    registry.register(GrepTool())
    registry.register(GitStatusTool())
    registry.register(GitDiffTool())
    registry.register(GitCommitTool())
    registry.register(BrowserTool())
    registry.register(APITool())
    return registry


__all__ = [
    "APITool",
    "BrowserTool",
    "FileDeleteTool",
    "FileEditTool",
    "FileReadTool",
    "FileWriteTool",
    "GitCommitTool",
    "GitDiffTool",
    "GitStatusTool",
    "GrepTool",
    "TerminalTool",
    "Tool",
    "ToolParam",
    "ToolRegistry",
    "ToolResult",
    "ToolStatus",
    "create_default_registry",
]
