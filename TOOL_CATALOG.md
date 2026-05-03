# Nexus Skill-Core — Tool Catalog

A centralized, MCP-compliant tool library that aggregates the best capabilities from **Claude Code**, **Gemini CLI**, and **Codex**, all routed through **NVIDIA NIM** for LLM-driven reasoning.

**Total tools**: 17  
**Protocol**: Model Context Protocol (MCP) — JSON-RPC 2.0  
**LLM Backend**: NVIDIA NIM (`integrate.api.nvidia.com/v1`)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                  MCP Server                      │
│              (FastAPI + JSON-RPC)                │
├─────────────────────────────────────────────────┤
│                 SkillStore                       │
│  ┌───────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ Discovery  │ │   Auth   │ │  Sandboxing  │   │
│  │ JSON/YAML  │ │  Manager │ │    Layer     │   │
│  └───────────┘ └──────────┘ └──────────────┘   │
├─────────────────────────────────────────────────┤
│              MCPTool Base Class                  │
│    name | description | input_schema | execute  │
├─────────────────────────────────────────────────┤
│            NvidiaToolWrapper                     │
│     reason() | code_transform() | explain()     │
│        NVIDIA NIM (llama-3.1-405b)              │
└─────────────────────────────────────────────────┘
```

---

## Filesystem Tools (5 tools)

| Tool | Source | API Key | Description |
|------|--------|---------|-------------|
| `read_file` | Claude + Gemini | No | Read file contents with optional line offset/limit |
| `write_file` | Claude + Gemini | No | Write content to a file, creating directories as needed |
| `list_directory` | Gemini | No | List files and subdirectories with glob filtering |
| `find_files` | Gemini | No | Find files matching glob patterns recursively |
| `replace_in_file` | Claude + Gemini | No | Replace exact string occurrences in a file |

### `read_file`
**Source**: Claude Code (ReadFile) + Gemini CLI (read_file)  
**Optimization**: Combined Claude's permission model with Gemini's offset/limit support for large file handling. Adds metadata header with total line count.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | Path to the file to read |
| `offset` | integer | No | Start line (0-based) |
| `limit` | integer | No | Max lines to read |

### `write_file`
**Source**: Claude Code (Edit/WriteFile) + Gemini CLI (write_file)  
**Optimization**: Auto-creates parent directories. UTF-8 encoding enforced.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | Path to the file |
| `content` | string | Yes | Content to write |

### `list_directory`
**Source**: Gemini CLI (list_directory/ReadFolder)  
**Optimization**: Added comma-separated ignore patterns for noise directories.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `dir_path` | string | Yes | Directory path |
| `ignore` | string | No | Comma-separated glob patterns to exclude |

### `find_files`
**Source**: Gemini CLI (glob/FindFiles)  
**Optimization**: Auto-filters .git, node_modules, __pycache__. Results sorted by modification time (newest first). Capped at 100 results.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pattern` | string | Yes | Glob pattern (e.g. `*.py`, `src/**/*.js`) |
| `path` | string | No | Directory to search in |

### `replace_in_file`
**Source**: Claude Code (Edit) + Gemini CLI (replace)  
**Optimization**: Safety check — refuses to replace if multiple occurrences found unless `allow_multiple=true`. Prevents accidental mass edits.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | File path |
| `old_string` | string | Yes | Text to find |
| `new_string` | string | Yes | Replacement text |
| `allow_multiple` | boolean | No | Replace all occurrences |

---

## Terminal Tools (1 tool)

| Tool | Source | API Key | Description |
|------|--------|---------|-------------|
| `execute_bash` | Claude + Codex | No | Execute shell commands through safety sandbox |

### `execute_bash`
**Source**: Claude Code (Bash) + Codex (terminal execution)  
**Optimization**: All commands pass through `Sandbox` safety layer that blocks destructive operations (rm -rf /, mkfs, etc.). Output truncated at 50KB. Configurable timeout.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `command` | string | Yes | Shell command to execute |
| `cwd` | string | No | Working directory |
| `timeout` | integer | No | Timeout in seconds (default 30) |

**Blocked commands**: `rm -rf /`, `mkfs`, `dd if=/dev/zero`, fork bombs, `chmod -R 777 /`, `shutdown`, `reboot`

---

## Search Tools (3 tools)

| Tool | Source | API Key | Description |
|------|--------|---------|-------------|
| `grep_search` | Claude + Gemini | No | Search file contents with regex via ripgrep |
| `web_search` | Gemini | No | Web search via DuckDuckGo (free) |
| `semantic_search` | Gemini + Codex | Optional | Natural language code search with NIM ranking |

### `grep_search`
**Source**: Claude Code (Grep) + Gemini CLI (grep_search/SearchText)  
**Optimization**: Uses `rg` (ripgrep) for speed, falls back to system `grep`. Supports file glob filtering and case-insensitive mode.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pattern` | string | Yes | Regex pattern |
| `path` | string | No | Directory to search |
| `include` | string | No | File glob filter |
| `case_insensitive` | boolean | No | Case-insensitive mode |
| `max_results` | integer | No | Max matches (default 100) |

### `web_search`
**Source**: Gemini CLI (Google Search integration)  
**Optimization**: Replaced paid Google Search API with **DuckDuckGo** (`duckduckgo_search` library). Free, no API key required. Returns titles, URLs, and snippets.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search query |
| `max_results` | integer | No | Max results (default 5) |

**Dependency**: `pip install duckduckgo_search`

### `semantic_search`
**Source**: Gemini CLI (semantic search) + Codex (code understanding)  
**Optimization**: Two-stage pipeline — keyword extraction → ripgrep candidates → NVIDIA NIM semantic ranking. Works without API key (returns unranked grep results as fallback).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Natural language query |
| `path` | string | No | Directory to search |
| `file_pattern` | string | No | File glob (default `*.py`) |
| `max_results` | integer | No | Max results (default 10) |

---

## Git Tools (4 tools)

| Tool | Source | API Key | Description |
|------|--------|---------|-------------|
| `git_status` | Claude | No | Show working tree status |
| `git_diff` | Claude | No | Show changes between commits/working dir |
| `git_log` | Claude + Codex | No | Show commit history |
| `git_commit` | Claude + Codex | No | Stage and commit changes |

### `git_status`
**Source**: Claude Code  
**Optimization**: Short format output for concise agent consumption.

### `git_diff`
**Source**: Claude Code  
**Optimization**: Added `staged` parameter for `--cached` diffs.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ref` | string | No | Git ref to diff against |
| `staged` | boolean | No | Show staged changes only |
| `cwd` | string | No | Repository directory |

### `git_log`
**Source**: Claude Code + Codex  
**Optimization**: Supports one-line and full format, file path filtering.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `max_count` | integer | No | Max commits (default 20) |
| `oneline` | boolean | No | One-line format (default true) |
| `path` | string | No | Filter by file/directory |
| `cwd` | string | No | Repository directory |

### `git_commit`
**Source**: Claude Code + Codex  
**Optimization**: Supports selective file staging instead of `git add -A` only.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | Yes | Commit message |
| `files` | string | No | Files to stage (space-separated, or `.` for all) |
| `cwd` | string | No | Repository directory |

---

## Code Intelligence Tools (4 tools)

| Tool | Source | API Key | Description |
|------|--------|---------|-------------|
| `code_refactor` | Codex | **Yes** | AI-powered code transformation |
| `code_explain` | Codex | **Yes** | AI-powered code explanation |
| `code_review` | Codex | **Yes** | AI-powered code review |
| `suggest_fix` | Codex | **Yes** | AI-powered bug fix suggestion |

**All code intelligence tools require `NVIDIA_API_KEY`** — reasoning is powered by NVIDIA NIM (default model: `nvidia/llama-3.1-405b-instruct`).

### `code_refactor`
**Source**: Codex (code modernization/transformation)  
**Optimization**: Auto-detects language from file extension. Writes result directly to file. Supports 10+ languages.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | File to refactor |
| `instruction` | string | Yes | Refactoring instruction |
| `language` | string | No | Language (auto-detected) |

### `code_explain`
**Source**: Codex (code understanding)  
**Optimization**: Supports line range selection for explaining specific functions/classes.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | File to explain |
| `start_line` | integer | No | Start line (1-based) |
| `end_line` | integer | No | End line (1-based) |

### `code_review`
**Source**: Codex  
**Optimization**: Structured JSON output with severity, line numbers, and overall quality score. Supports focused review on specific concern areas.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | File to review |
| `focus` | string | No | Focus: bugs, security, performance, style, all |

### `suggest_fix`
**Source**: Codex (debugging/self-healing)  
**Optimization**: Can optionally apply the fix directly to the file. Multi-language support.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | File with the error |
| `error_message` | string | Yes | Error/traceback text |
| `apply` | boolean | No | Apply fix directly (default false) |

---

## NVIDIA NIM Integration

All LLM-driven reasoning goes through `NvidiaToolWrapper`:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="$NVIDIA_API_KEY"
)
```

### Available Methods

| Method | Purpose |
|--------|---------|
| `reason()` | General text reasoning |
| `reason_json()` | Structured JSON reasoning |
| `code_transform()` | Code refactoring/transformation |
| `explain_code()` | Code explanation |
| `suggest_fix()` | Error diagnosis and fix |
| `semantic_search_rank()` | Rank search results by relevance |

### Supported Models

- `nvidia/llama-3.1-405b-instruct` (default)
- `nvidia/nemotron-4-340b-instruct`
- All models available on NVIDIA NIM

---

## SkillStore — Unified Registry

```python
from nexus.mcp import SkillStore
from nexus.mcp.tools import ALL_MCP_TOOLS

store = SkillStore()
store.register_all(ALL_MCP_TOOLS)

# Execute a tool
result = store.execute("read_file", file_path="/path/to/file.py")

# Load custom tools from JSON/YAML
store.load_from_json("custom_tools.json")
store.load_from_yaml("custom_tools.yaml")
```

### Custom Tool Definition (JSON)

```json
[
  {
    "name": "lint_python",
    "description": "Run ruff linter on a Python file",
    "category": "terminal",
    "source": "custom",
    "parameters": [
      {"name": "file_path", "type": "string", "description": "File to lint"}
    ],
    "command_template": "ruff check {file_path}"
  }
]
```

---

## MCP Server

Start the server:

```python
from nexus.mcp import MCPServer

server = MCPServer()
app = server.create_app()
# Run with: uvicorn nexus.mcp.server:app
```

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with tool count |
| `/tools` | GET | List all tools with schemas |
| `/mcp` | POST | JSON-RPC 2.0 MCP endpoint |
| `/tools/{name}` | POST | Direct tool execution |

### JSON-RPC Methods

| Method | Description |
|--------|-------------|
| `initialize` | Server handshake |
| `tools/list` | Enumerate tools |
| `tools/call` | Execute a tool |

---

## Dependencies

| Dependency | Required | Purpose |
|------------|----------|---------|
| `openai` | For code tools | NVIDIA NIM client |
| `pydantic` | Yes | Schema validation |
| `fastapi` | For server | MCP server |
| `httpx` | For web tools | HTTP requests |
| `pyyaml` | For YAML loading | Tool definitions |
| `duckduckgo_search` | For web_search | Free web search |
| `tenacity` | For retries | API retry logic |

---

## Free Alternatives Used

| Original (Paid) | Replacement (Free) | Notes |
|------------------|--------------------|-------|
| Google Search API | `duckduckgo_search` | No API key needed |
| OpenAI Embeddings | Keyword + ripgrep | Fallback semantic search |
| Paid code analysis | NVIDIA NIM (free tier) | Requires NVIDIA_API_KEY |
