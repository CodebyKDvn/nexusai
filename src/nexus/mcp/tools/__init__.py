"""MCP-compliant atomic tools aggregated from Claude Code, Gemini CLI, and Codex."""

from nexus.mcp.tools.code_tools import (
    CodeExplainTool,
    CodeRefactorTool,
    CodeReviewTool,
    SuggestFixTool,
)
from nexus.mcp.tools.filesystem_tools import (
    FindFilesTool,
    ListDirectoryTool,
    ReadFileTool,
    ReplaceInFileTool,
    WriteFileTool,
)
from nexus.mcp.tools.git_tools import (
    GitCommitMCPTool,
    GitDiffMCPTool,
    GitLogTool,
    GitStatusMCPTool,
)
from nexus.mcp.tools.search_tools import (
    GrepSearchTool,
    SemanticSearchTool,
    WebSearchTool,
)
from nexus.mcp.tools.terminal_tools import ExecuteBashTool

ALL_MCP_TOOLS = [
    # Filesystem (Claude + Gemini)
    ReadFileTool(),
    WriteFileTool(),
    ListDirectoryTool(),
    FindFilesTool(),
    ReplaceInFileTool(),
    # Terminal (Claude + Codex)
    ExecuteBashTool(),
    # Search (Claude + Gemini)
    GrepSearchTool(),
    WebSearchTool(),
    SemanticSearchTool(),
    # Git (Claude + Codex)
    GitStatusMCPTool(),
    GitDiffMCPTool(),
    GitLogTool(),
    GitCommitMCPTool(),
    # Code Intelligence (Codex)
    CodeRefactorTool(),
    CodeExplainTool(),
    CodeReviewTool(),
    SuggestFixTool(),
]

__all__ = [
    "ALL_MCP_TOOLS",
    "CodeExplainTool",
    "CodeRefactorTool",
    "CodeReviewTool",
    "ExecuteBashTool",
    "FindFilesTool",
    "GitCommitMCPTool",
    "GitDiffMCPTool",
    "GitLogTool",
    "GitStatusMCPTool",
    "GrepSearchTool",
    "ListDirectoryTool",
    "ReadFileTool",
    "ReplaceInFileTool",
    "SemanticSearchTool",
    "SuggestFixTool",
    "WebSearchTool",
    "WriteFileTool",
]
