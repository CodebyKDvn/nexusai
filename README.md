# Nexus AI

**Multi-Agent AI Development Platform** — An autonomous AI Dev Team that understands intent, plans work, writes code, tests, debugs, and learns.

## Features

- **10 Specialized Agents** — Orchestrator, Planner, Developer, Debugger, QA, Research, Memory, Critic, and Tool Executor
- **Intelligent Task Routing** — Automatically delegates tasks to the right specialist
- **Persistent Memory** — Short-term context + long-term vector storage with RAG retrieval
- **Tool System** — File operations, terminal execution, git, code search, web browsing, API calls
- **LLM Integration** — OpenAI and Anthropic providers with retry, token tracking, and function calling
- **Self-Improvement** — Critic agent evaluates outputs and stores lessons for future tasks
- **Rich Terminal UI** — Interactive CLI with status panels, plan visualization, and evaluation reports

## Architecture

```
User Request
    │
    ▼
Orchestrator ──► Planner ──► Developer(s)
    │                            │
    ├──► Debugger ◄──────────────┘
    ├──► QA Agent
    ├──► Research Agent
    ├──► Critic Agent ──► Memory Agent
    │
    ▼
Final Result
```

All agents communicate via a typed message bus and follow the execution loop:
**Understand → Plan → Act → Observe → Reflect → Improve → Repeat**

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system design.

## Quick Start

### Installation

```bash
pip install -e ".[dev]"
```

### Configuration

Set your LLM API key:

```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# Or Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Interactive Mode

```bash
nexus
```

This launches the interactive REPL where you can submit tasks to the AI dev team:

```
nexus> Plan a REST API for user management
nexus> Build a todo app with React and FastAPI
nexus> Fix the bug in the authentication module
```

### Single Command

```bash
nexus run "Build a CLI tool for file management"
```

### Initialize Project Config

```bash
nexus init
```

Creates `.nexus/config.yaml` with default settings.

## CLI Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/status` | System status (agents, memory, iterations) |
| `/agents` | List active agents |
| `/memory [query]` | Search persistent memory |
| `/config` | Show current configuration |
| `/clear` | Clear short-term memory |
| `/quit` | Exit |

## Configuration

Edit `.nexus/config.yaml`:

```yaml
llm:
  provider: openai        # or "anthropic"
  model: gpt-4o           # or "claude-sonnet-4-20250514"
  temperature: 0.2
  max_tokens: 4096

memory:
  persist_dir: .nexus/memory
  short_term_capacity: 50

sandbox:
  enabled: true
  timeout_seconds: 30

max_iterations: 20
log_level: INFO
```

## Agent Roles

| Agent | Role |
|-------|------|
| **Orchestrator** | Receives requests, clarifies intent, delegates work, tracks progress |
| **Planner** | Breaks tasks into structured plans with milestones and dependencies |
| **Developer** | Writes code, designs APIs, implements features |
| **Debugger** | Analyzes errors, traces bugs, proposes and applies fixes |
| **QA** | Writes tests, runs test suites, validates correctness |
| **Research** | Searches docs, codebases, and web for relevant knowledge |
| **Memory** | Stores and retrieves patterns, decisions, bugs, and preferences |
| **Critic** | Evaluates output quality, scores on 6 criteria, drives improvement |
| **Tool Executor** | Executes file ops, terminal commands, git, search, API calls |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## Rule-Based Mode

Nexus AI works without an LLM API key using rule-based fallbacks:
- The Orchestrator routes tasks by keyword matching
- The Planner generates structured plans using templates
- Agents return stub responses with actionable suggestions

This is useful for testing the framework and understanding the agent architecture without incurring API costs.

## License

MIT
