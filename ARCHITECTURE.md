# Nexus AI — System Architecture

## Overview

Nexus AI is a multi-agent AI development platform that operates as an autonomous "AI Dev Team." It coordinates specialized agents — each powered by a dedicated NVIDIA NIM model — to understand intent, plan work, write code, test, debug, and deploy, learning from each interaction.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                      CLI / UI Layer                      │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Rich TUI    │  │  Session Mgr │  │  Config Mgr   │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬───────┘  │
└─────────┼────────────────┼──────────────────┼───────────┘
          │                │                  │
┌─────────▼────────────────▼──────────────────▼───────────┐
│                   Orchestrator Agent                     │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────┐   │
│  │ Task Queue  │  │ Delegation │  │ Global State Mgr │   │
│  └─────┬──────┘  └─────┬──────┘  └────────┬─────────┘  │
└────────┼───────────────┼──────────────────┼─────────────┘
         │               │                  │
┌────────▼───────────────▼──────────────────▼─────────────┐
│                    Agent Layer (10 Agents)               │
│  ┌──────────┐ ┌──────────────┐ ┌───────────────┐        │
│  │ Planner  │ │ Frontend Dev │ │ Backend Dev   │        │
│  └──────────┘ └──────────────┘ └───────────────┘        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ Debugger │ │   QA     │ │ Research │ │  Critic  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
│  ┌──────────┐ ┌──────────────┐                          │
│  │  Memory  │ │ Tool Executor│                          │
│  └──────────┘ └──────────────┘                          │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  Message Bus                             │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────┐   │
│  │ Pub/Sub    │  │ Routing    │  │ Event History    │   │
│  └────────────┘  └────────────┘  └──────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                Infrastructure Layer                      │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Tool Mgr │ │ NVIDIA NIM│ │ Memory   │ │ Sandbox  │  │
│  │          │ │ LLM Pool  │ │ Store    │ │          │  │
│  └──────────┘ └───────────┘ └──────────┘ └──────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Per-Agent Model Assignment

Each agent is assigned a specific NVIDIA NIM model via the OpenAI-compatible API at `https://integrate.api.nvidia.com/v1`:

| Agent | Model | Reason |
|-------|-------|--------|
| Orchestrator | `moonshotai/kimi-k2-5` | Strong reasoning for task decomposition and delegation |
| Planner | `z-ai/glm5.1` | Structured output generation for plans and milestones |
| Frontend Developer | `minimaxai/minimax-m2.7` | MoE model excelling at UI/frontend code generation |
| Backend Developer | `deepseek-ai/deepseek-v4-pro` | Top-tier code generation for APIs, databases, services |
| Debugger | `deepseek-ai/deepseek-v4-flash` | Fast inference for iterative debugging cycles |
| QA | `google/gemma-4-31b-it` | Instruction-tuned model for test generation and validation |
| Research | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | Omnimodal reasoning for documentation and knowledge retrieval |
| Memory | `qwen/qwen3.5-397b-a17b` | Large-context MoE model for pattern matching and retrieval |
| Critic | `deepseek-ai/deepseek-v3.2` | Analytical model for code quality evaluation |
| Tool Executor | `mistralai/mistral-nemotron` | Efficient function-calling model for tool dispatch |

## Agent Communication Protocol

All agents communicate via a typed message bus:

```python
Message {
    id: UUID
    sender: AgentId
    recipient: AgentId | Broadcast
    type: TaskRequest | TaskResult | Query | Event | Error
    payload: dict
    metadata: {timestamp, priority, correlation_id}
}
```

Messages are routed by the bus. The Orchestrator subscribes to all channels; other agents subscribe to their own + broadcast.

## Agent Execution Loop

Every agent follows the same core loop:

```
RECEIVE message
  → UNDERSTAND (parse intent, check memory)
  → PLAN (decompose into steps)
  → ACT (execute tools, call LLM)
  → OBSERVE (capture outputs, errors)
  → REFLECT (evaluate quality, store learnings)
  → RESPOND (send result message)
```

## Memory System

### Short-Term Memory
- In-process context window per agent
- Stores current task state, recent messages, tool outputs
- Cleared between top-level tasks

### Long-Term Memory
- ChromaDB vector store for semantic retrieval
- Collections: `code_patterns`, `decisions`, `bugs`, `user_preferences`
- Automatic embedding of agent reflections
- RAG retrieval before every planning step

## Tool System

Standardized interface for all external operations:

```python
class Tool(ABC):
    name: str
    description: str

    def execute(self, **params) -> ToolResult:
        """Execute the tool and return structured output."""

    def validate_params(self, **params) -> bool:
        """Validate parameters before execution."""
```

Tools: FileOps, Terminal, Git, CodeSearch, Browser, API

## LLM Integration

Provider-agnostic abstraction supporting:
- **NVIDIA NIM** (primary) — per-agent model assignment via OpenAI-compatible API
- OpenAI (GPT-4, GPT-4o) — legacy fallback
- Anthropic (Claude 3.5 Sonnet, Claude 4) — legacy fallback

Features:
- Automatic retry with exponential backoff
- Token tracking and budget management
- Tool/function calling
- Per-agent model specialization

## Self-Improvement

After each task completion:
1. Critic agent evaluates the output quality
2. Scores are stored alongside the task in memory
3. Patterns from high-scoring solutions are extracted
4. Future planning retrieves these patterns via RAG
