"""Observability — tracing, metrics, and performance monitoring.

Provides structured tracing for agent conversations, token usage tracking,
latency measurement, and cost estimation.  Data is stored in JSONL files
and can be queried for dashboards.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SpanKind(StrEnum):
    """Types of traced operations."""

    AGENT_CALL = "agent_call"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    WORKFLOW_PHASE = "workflow_phase"
    MESSAGE_BUS = "message_bus"
    RECOVERY = "recovery"
    EVALUATION = "evaluation"


@dataclass
class Span:
    """A single traced operation within a trace."""

    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    trace_id: str = ""
    parent_span_id: str = ""
    kind: SpanKind = SpanKind.AGENT_CALL
    name: str = ""
    agent_id: str = ""
    model: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    status: str = "ok"
    error: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    token_usage: dict[str, int] = field(default_factory=dict)

    def finish(self, status: str = "ok", error: str = "") -> None:
        self.end_time = time.monotonic()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.status = status
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "kind": self.kind.value,
            "name": self.name,
            "agent_id": self.agent_id,
            "model": self.model,
            "start_time": self.start_time,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "error": self.error,
            "attributes": self.attributes,
            "token_usage": self.token_usage,
        }


@dataclass
class Trace:
    """A complete trace of a request through the system."""

    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    task: str = ""
    spans: list[Span] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    total_duration_ms: float = 0.0
    total_tokens: dict[str, int] = field(default_factory=dict)
    status: str = "in_progress"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def add_span(self, span: Span) -> None:
        span.trace_id = self.trace_id
        self.spans.append(span)

    def finish(self, status: str = "ok") -> None:
        self.end_time = time.monotonic()
        self.total_duration_ms = (self.end_time - self.start_time) * 1000
        self.status = status
        self._aggregate_tokens()

    def _aggregate_tokens(self) -> None:
        totals: dict[str, int] = defaultdict(int)
        for span in self.spans:
            for key, val in span.token_usage.items():
                totals[key] += val
        self.total_tokens = dict(totals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "task": self.task[:200],
            "spans": [s.to_dict() for s in self.spans],
            "total_duration_ms": round(self.total_duration_ms, 2),
            "total_tokens": self.total_tokens,
            "status": self.status,
            "created_at": self.created_at,
        }


# Cost estimates per 1M tokens (in USD) — configurable
DEFAULT_COST_TABLE: dict[str, dict[str, float]] = {
    "deepseek-ai/deepseek-v4-pro": {"input": 0.50, "output": 2.00},
    "deepseek-ai/deepseek-v4-flash": {"input": 0.20, "output": 0.80},
    "moonshotai/kimi-k2-instruct": {"input": 0.30, "output": 1.20},
    "z-ai/glm-5.1": {"input": 0.25, "output": 1.00},
    "minimaxai/minimax-m2.7": {"input": 0.40, "output": 1.50},
    "google/gemma-4-31b-it": {"input": 0.10, "output": 0.40},
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": {"input": 0.15, "output": 0.60},
    "default": {"input": 0.30, "output": 1.00},
}


@dataclass
class CostEstimate:
    """Estimated cost for a set of LLM calls."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    model: str = ""
    currency: str = "USD"

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "model": self.model,
        }


class CostTracker:
    """Tracks and estimates LLM usage costs."""

    def __init__(
        self,
        cost_table: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self._cost_table = cost_table or DEFAULT_COST_TABLE
        self._estimates: list[CostEstimate] = []

    def estimate(
        self,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> CostEstimate:
        """Estimate cost for a single LLM call."""
        rates = self._cost_table.get(model, self._cost_table.get("default", {}))
        input_rate = rates.get("input", 0.30)
        output_rate = rates.get("output", 1.00)

        estimate = CostEstimate(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_cost_usd=input_tokens * input_rate / 1_000_000,
            output_cost_usd=output_tokens * output_rate / 1_000_000,
            model=model,
        )
        estimate.total_cost_usd = estimate.input_cost_usd + estimate.output_cost_usd
        self._estimates.append(estimate)
        return estimate

    def total_cost(self) -> float:
        return sum(e.total_cost_usd for e in self._estimates)

    def summary(self) -> dict[str, Any]:
        if not self._estimates:
            return {"total_cost_usd": 0.0, "total_calls": 0}
        by_model: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"calls": 0, "tokens": 0, "cost_usd": 0.0}
        )
        for e in self._estimates:
            by_model[e.model]["calls"] += 1
            by_model[e.model]["tokens"] += e.total_tokens
            by_model[e.model]["cost_usd"] += e.total_cost_usd
        return {
            "total_cost_usd": round(self.total_cost(), 6),
            "total_calls": len(self._estimates),
            "total_tokens": sum(e.total_tokens for e in self._estimates),
            "by_model": dict(by_model),
        }


class AgentMetrics:
    """Per-agent performance metrics."""

    def __init__(self) -> None:
        self._call_counts: dict[str, int] = defaultdict(int)
        self._error_counts: dict[str, int] = defaultdict(int)
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._token_totals: dict[str, int] = defaultdict(int)

    def record_call(
        self,
        agent_id: str,
        duration_ms: float,
        tokens: int = 0,
        success: bool = True,
    ) -> None:
        self._call_counts[agent_id] += 1
        self._latencies[agent_id].append(duration_ms)
        self._token_totals[agent_id] += tokens
        if not success:
            self._error_counts[agent_id] += 1

    def get_stats(self, agent_id: str) -> dict[str, Any]:
        calls = self._call_counts.get(agent_id, 0)
        if calls == 0:
            return {"agent_id": agent_id, "calls": 0}
        latencies = self._latencies.get(agent_id, [])
        return {
            "agent_id": agent_id,
            "calls": calls,
            "errors": self._error_counts.get(agent_id, 0),
            "error_rate": self._error_counts.get(agent_id, 0) / calls,
            "total_tokens": self._token_totals.get(agent_id, 0),
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
            "p50_latency_ms": sorted(latencies)[len(latencies) // 2] if latencies else 0,
            "p99_latency_ms": sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0,
        }

    def all_stats(self) -> dict[str, dict[str, Any]]:
        return {agent_id: self.get_stats(agent_id) for agent_id in self._call_counts}


class TraceStore:
    """Persists and queries traces.

    Traces are stored as newline-delimited JSON in
    ``.nexus_metrics/traces.jsonl``.
    """

    def __init__(self, metrics_dir: str | Path = ".nexus_metrics") -> None:
        self.metrics_dir = Path(metrics_dir)
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        self._trace_file = self.metrics_dir / "traces.jsonl"
        self._traces: list[Trace] = []

    def store(self, trace: Trace) -> None:
        self._traces.append(trace)
        with open(self._trace_file, "a") as f:
            f.write(json.dumps(trace.to_dict(), default=str) + "\n")

    def recent(self, limit: int = 20) -> list[Trace]:
        return list(self._traces[-limit:])

    def get_trace(self, trace_id: str) -> Trace | None:
        for t in self._traces:
            if t.trace_id == trace_id:
                return t
        return None

    def load_history(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self._trace_file.exists():
            return []
        results: list[dict[str, Any]] = []
        with open(self._trace_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return results[-limit:]


class Tracer:
    """Central observability hub — creates traces and spans.

    Usage::

        tracer = Tracer()
        trace = tracer.start_trace("Build login page")
        span = tracer.start_span(trace, SpanKind.AGENT_CALL, "orchestrator")
        # ... do work ...
        span.finish()
        trace.finish()
    """

    def __init__(
        self,
        trace_store: TraceStore | None = None,
        cost_tracker: CostTracker | None = None,
        agent_metrics: AgentMetrics | None = None,
    ) -> None:
        self.store = trace_store or TraceStore()
        self.costs = cost_tracker or CostTracker()
        self.metrics = agent_metrics or AgentMetrics()
        self._active_traces: dict[str, Trace] = {}

    def start_trace(self, task: str = "") -> Trace:
        trace = Trace(task=task, start_time=time.monotonic())
        self._active_traces[trace.trace_id] = trace
        return trace

    def start_span(
        self,
        trace: Trace,
        kind: SpanKind,
        name: str,
        agent_id: str = "",
        model: str = "",
        parent_span_id: str = "",
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        span = Span(
            trace_id=trace.trace_id,
            parent_span_id=parent_span_id,
            kind=kind,
            name=name,
            agent_id=agent_id,
            model=model,
            start_time=time.monotonic(),
            attributes=attributes or {},
        )
        trace.add_span(span)
        return span

    def finish_span(
        self,
        span: Span,
        status: str = "ok",
        error: str = "",
        token_usage: dict[str, int] | None = None,
    ) -> None:
        span.finish(status=status, error=error)
        if token_usage:
            span.token_usage = token_usage

        self.metrics.record_call(
            agent_id=span.agent_id or span.name,
            duration_ms=span.duration_ms,
            tokens=sum(span.token_usage.values()),
            success=status == "ok",
        )

        if token_usage and span.model:
            self.costs.estimate(
                model=span.model,
                input_tokens=token_usage.get("prompt_tokens", 0),
                output_tokens=token_usage.get("completion_tokens", 0),
            )

    def finish_trace(self, trace: Trace, status: str = "ok") -> None:
        trace.finish(status=status)
        self._active_traces.pop(trace.trace_id, None)
        self.store.store(trace)

    def summary(self) -> dict[str, Any]:
        return {
            "active_traces": len(self._active_traces),
            "total_traces": len(self.store._traces),
            "costs": self.costs.summary(),
            "agents": self.metrics.all_stats(),
        }
