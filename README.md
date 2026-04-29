# Nexus AI

**Multi-Agent AI Development Platform** — An autonomous AI Dev Team that understands intent, plans work, writes code, tests, debugs, and learns.

## Features

- **11 Specialized Agents** — Orchestrator, Planner, UX/UI Designer, Frontend Developer, Backend Developer, Debugger, QA, Research, Memory, Critic, and Tool Executor
- **NVIDIA NIM Integration** — Each agent is powered by a dedicated NVIDIA NIM model optimized for its role
- **Intelligent Task Routing** — Automatically delegates tasks to the right specialist (frontend vs backend, debug, test, etc.)
- **Persistent Memory** — Short-term context + long-term vector storage with RAG retrieval
- **Tool System** — File operations, terminal execution, git, code search, web browsing, API calls
- **Self-Improvement** — Critic agent evaluates outputs and stores lessons for future tasks
- **Rich Terminal UI** — Interactive CLI with status panels, plan visualization, and evaluation reports

## Architecture

```
User Request
    │
    ▼
Orchestrator ──► Planner ──► UX/UI Designer ──► Frontend Developer
    │                    └──► Backend Developer
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

Set your NVIDIA NIM API key:

```bash
export NVIDIA_API_KEY="nvapi-..."
```

### Interactive Mode

```bash
nexus
```

This launches the interactive REPL where you can submit tasks to the AI dev team:

```
nexus> Plan a REST API for user management
nexus> Design a prototype for the user dashboard
nexus> Build a React component for user authentication
nexus> Create a REST API backend for user management
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
  provider: nvidia          # "nvidia" (default), "openai", or "anthropic"
  model: deepseek-ai/deepseek-v4-pro
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

## Agent Roles & Models

Each agent is assigned a specialized NVIDIA NIM model:

| Agent | Role | NVIDIA NIM Model |
|-------|------|------------------|
| **Orchestrator** | Receives requests, clarifies intent, delegates work | `moonshotai/kimi-k2-5` |
| **Planner** | Breaks tasks into structured plans with milestones | `z-ai/glm5.1` |
| **UX/UI Designer** | Designs prototypes, visual systems using [Huashu Design](https://github.com/alchaincyf/huashu-design) principles — 20 design philosophies, 5-dimension review, anti-AI-slop rules | `moonshotai/kimi-k2-5` |
| **Frontend Developer** | Builds UIs, components, CSS, client-side logic | `minimaxai/minimax-m2.7` |
| **Backend Developer** | Builds APIs, databases, server-side services | `deepseek-ai/deepseek-v4-pro` |
| **Debugger** | Analyzes errors, traces bugs, applies fixes | `deepseek-ai/deepseek-v4-flash` |
| **QA** | Writes tests, validates correctness | `google/gemma-4-31b-it` |
| **Research** | Searches docs, codebases, and web for knowledge | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` |
| **Memory** | Stores and retrieves patterns, decisions, bugs | `qwen/qwen3.5-397b-a17b` |
| **Critic** | Evaluates output quality, drives improvement | `deepseek-ai/deepseek-v3.2` |
| **Tool Executor** | Executes file ops, terminal, git, search, API calls | `mistralai/mistral-nemotron` |

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
