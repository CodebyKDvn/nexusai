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
from nexus.tools.gitnexus import GITNEXUS_TOOLS, is_gitnexus_available
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

    # Register GitNexus code intelligence tools when available
    if is_gitnexus_available():
        for tool in GITNEXUS_TOOLS:
            registry.register(tool)

    return registry


__all__ = [
    "APITool",
    "BrowserTool",
    "FileDeleteTool",
    "FileEditTool",
    "FileReadTool",
    "FileWriteTool",
    "GITNEXUS_TOOLS",
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
    "is_gitnexus_available",
]
