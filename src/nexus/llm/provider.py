"""LLM provider interface and factory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMMessage:
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    finish_reason: str = ""

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """Abstract LLM provider."""

    @abstractmethod
    def chat(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a chat completion request."""

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string."""


def create_provider(provider: str, api_key: str, model: str) -> LLMProvider:
    """Factory for creating LLM providers."""
    if provider == "nvidia":
        from nexus.llm.nvidia_provider import NvidiaProvider

        return NvidiaProvider(api_key=api_key, model=model)
    elif provider == "openai":
        from nexus.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=api_key, model=model)
    elif provider == "anthropic":
        from nexus.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=api_key, model=model)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
