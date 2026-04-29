# Nexus AI — System Architecture

## Overview

Nexus AI is a multi-agent AI development platform that operates as an autonomous "AI Dev Team." It coordinates specialized agents to understand intent, plan work, write code, test, debug, and deploy — learning from each interaction.

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
│                    Agent Layer                           │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Planner  │ │ Developer │ │ Debugger │ │   QA     │  │
│  └──────────┘ └───────────┘ └──────────┘ └──────────┘  │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐               │
│  │ Research │ │  Critic   │ │  Memory  │               │
│  └──────────┘ └───────────┘ └──────────┘               │
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
│  │ Tool Mgr │ │ LLM Pool  │ │ Memory   │ │ Sandbox  │  │
│  │          │ │           │ │ Store    │ │          │  │
│  └──────────┘ └───────────┘ └──────────┘ └──────────┘  │
└─────────────────────────────────────────────────────────┘
```

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
- OpenAI (GPT-4, GPT-4o)
- Anthropic (Claude 3.5 Sonnet, Claude 4)

Features:
- Automatic retry with backoff
- Token tracking and budget management
- Streaming support
- Tool/function calling

## Self-Improvement

After each task completion:
1. Critic agent evaluates the output quality
2. Scores are stored alongside the task in memory
3. Patterns from high-scoring solutions are extracted
4. Future planning retrieves these patterns via RAG
