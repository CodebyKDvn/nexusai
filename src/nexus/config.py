"""Configuration management for Nexus AI."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# NVIDIA NIM model assignments per agent role
NVIDIA_AGENT_MODELS: dict[str, str] = {
    "orchestrator": "moonshotai/kimi-k2-5",
    "planner": "z-ai/glm5.1",
    "frontend_developer": "minimaxai/minimax-m2.7",
    "backend_developer": "deepseek-ai/deepseek-v4-pro",
    "debugger": "deepseek-ai/deepseek-v4-flash",
    "qa": "google/gemma-4-31b-it",
    "research": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "memory": "qwen/qwen3.5-397b-a17b",
    "critic": "deepseek-ai/deepseek-v3.2",
    "tool_executor": "mistralai/mistral-nemotron",
}


@dataclass
class LLMConfig:
    provider: str = "nvidia"
    model: str = "deepseek-ai/deepseek-v4-pro"
    temperature: float = 0.2
    max_tokens: int = 4096
    api_key: str = ""

    def __post_init__(self) -> None:
        if not self.api_key:
            env_keys = {
                "nvidia": "NVIDIA_API_KEY",
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
            }
            env_key = env_keys.get(self.provider, "NVIDIA_API_KEY")
            self.api_key = os.environ.get(env_key, "")


@dataclass
class MemoryConfig:
    persist_dir: str = ".nexus/memory"
    short_term_capacity: int = 50
    embedding_model: str = "all-MiniLM-L6-v2"


@dataclass
class SandboxConfig:
    enabled: bool = True
    timeout_seconds: int = 30
    max_output_size: int = 10000


@dataclass
class NexusConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    project_dir: str = "."
    log_level: str = "INFO"
    max_iterations: int = 20

    @classmethod
    def load(cls, path: str | Path | None = None) -> NexusConfig:
        if path is None:
            path = Path(".nexus/config.yaml")
        path = Path(path)
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return cls(
                llm=LLMConfig(**data.get("llm", {})),
                memory=MemoryConfig(**data.get("memory", {})),
                sandbox=SandboxConfig(**data.get("sandbox", {})),
                project_dir=data.get("project_dir", "."),
                log_level=data.get("log_level", "INFO"),
                max_iterations=data.get("max_iterations", 20),
            )
        return cls()

    def save(self, path: str | Path | None = None) -> None:
        if path is None:
            path = Path(".nexus/config.yaml")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "llm": {
                "provider": self.llm.provider,
                "model": self.llm.model,
                "temperature": self.llm.temperature,
                "max_tokens": self.llm.max_tokens,
            },
            "memory": {
                "persist_dir": self.memory.persist_dir,
                "short_term_capacity": self.memory.short_term_capacity,
            },
            "sandbox": {
                "enabled": self.sandbox.enabled,
                "timeout_seconds": self.sandbox.timeout_seconds,
            },
            "project_dir": self.project_dir,
            "log_level": self.log_level,
            "max_iterations": self.max_iterations,
        }
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)
