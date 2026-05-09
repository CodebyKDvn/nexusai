"""Self-Evaluation Framework — benchmarking and metrics logging.

After each task, agents self-evaluate their output against quality
metrics and log structured performance data.  Supports pluggable
benchmark suites (HumanEval-style code challenges, review quality
checks, etc.).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class EvalDimension(StrEnum):
    """Dimensions along which agent output is evaluated."""

    CORRECTNESS = "correctness"
    COMPLETENESS = "completeness"
    CODE_QUALITY = "code_quality"
    PERFORMANCE = "performance"
    SECURITY = "security"
    READABILITY = "readability"
    TEST_COVERAGE = "test_coverage"
    DESIGN_QUALITY = "design_quality"


class BenchmarkType(StrEnum):
    """Categories of benchmarks."""

    CODE_GEN = "code_gen"
    CODE_REVIEW = "code_review"
    BUG_FIX = "bug_fix"
    PLANNING = "planning"
    DESIGN = "design"
    GENERAL = "general"


@dataclass
class EvalScore:
    """A score along a single dimension."""

    dimension: EvalDimension
    score: float  # 0.0 to 1.0
    weight: float = 1.0
    details: str = ""

    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class EvalResult:
    """Complete evaluation result for a task."""

    eval_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    task_id: str = ""
    agent_id: str = ""
    scores: list[EvalScore] = field(default_factory=list)
    overall_score: float = 0.0
    benchmark_type: BenchmarkType = BenchmarkType.GENERAL
    duration_ms: float = 0.0
    token_usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    passed: bool = False
    feedback: str = ""

    def compute_overall(self) -> float:
        """Compute weighted average of all dimension scores."""
        if not self.scores:
            return 0.0
        total_weight = sum(s.weight for s in self.scores)
        if total_weight == 0:
            return 0.0
        self.overall_score = sum(s.weighted_score() for s in self.scores) / total_weight
        return self.overall_score

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scores"] = [
            {
                "dimension": s.dimension.value,
                "score": s.score,
                "weight": s.weight,
                "details": s.details,
            }
            for s in self.scores
        ]
        data["benchmark_type"] = self.benchmark_type.value
        return data


@dataclass
class BenchmarkCase:
    """A single test case in a benchmark suite."""

    case_id: str
    description: str
    input_data: str
    expected_output: str = ""
    benchmark_type: BenchmarkType = BenchmarkType.GENERAL
    timeout_seconds: float = 60.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkSuite:
    """A collection of benchmark test cases."""

    suite_id: str
    name: str
    description: str = ""
    cases: list[BenchmarkCase] = field(default_factory=list)
    benchmark_type: BenchmarkType = BenchmarkType.GENERAL

    def add_case(self, case: BenchmarkCase) -> None:
        self.cases.append(case)


class MetricsLogger:
    """Logs evaluation metrics to disk for analysis.

    Metrics are stored as newline-delimited JSON in
    ``.nexus_metrics/evals.jsonl``.
    """

    def __init__(self, metrics_dir: str | Path = ".nexus_metrics") -> None:
        self.metrics_dir = Path(metrics_dir)
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self.metrics_dir / "evals.jsonl"
        self._entries: list[EvalResult] = []

    def log(self, result: EvalResult) -> None:
        """Log an evaluation result."""
        self._entries.append(result)
        with open(self._log_file, "a") as f:
            f.write(json.dumps(result.to_dict(), default=str) + "\n")
        logger.info(
            "Eval logged: %s agent=%s score=%.2f passed=%s",
            result.eval_id,
            result.agent_id,
            result.overall_score,
            result.passed,
        )

    def get_entries(self, limit: int = 50) -> list[EvalResult]:
        """Return recent evaluation entries from memory."""
        return list(self._entries[-limit:])

    def load_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Load evaluation history from disk."""
        if not self._log_file.exists():
            return []
        results: list[dict[str, Any]] = []
        with open(self._log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return results[-limit:]

    def agent_stats(self, agent_id: str) -> dict[str, Any]:
        """Compute aggregate stats for an agent."""
        agent_results = [e for e in self._entries if e.agent_id == agent_id]
        if not agent_results:
            return {"agent_id": agent_id, "total_evals": 0}
        scores = [e.overall_score for e in agent_results]
        return {
            "agent_id": agent_id,
            "total_evals": len(agent_results),
            "avg_score": sum(scores) / len(scores),
            "min_score": min(scores),
            "max_score": max(scores),
            "pass_rate": sum(1 for e in agent_results if e.passed) / len(agent_results),
            "total_tokens": sum(
                sum(e.token_usage.values()) for e in agent_results
            ),
        }

    def summary(self) -> dict[str, Any]:
        """Global summary of all evaluations."""
        if not self._entries:
            return {"total_evals": 0, "agents": {}}
        agents = {e.agent_id for e in self._entries}
        return {
            "total_evals": len(self._entries),
            "agents": {a: self.agent_stats(a) for a in sorted(agents)},
            "overall_avg": sum(e.overall_score for e in self._entries) / len(self._entries),
            "overall_pass_rate": sum(1 for e in self._entries if e.passed) / len(self._entries),
        }


class SelfEvaluator:
    """Evaluates agent output against quality dimensions.

    This is a rule-based evaluator.  When an LLM is available it can be
    extended to use LLM-as-judge for more nuanced scoring.
    """

    def __init__(
        self,
        metrics_logger: MetricsLogger | None = None,
        pass_threshold: float = 0.6,
    ) -> None:
        self.logger = metrics_logger or MetricsLogger()
        self.pass_threshold = pass_threshold
        self._benchmarks: dict[str, BenchmarkSuite] = {}

    def register_benchmark(self, suite: BenchmarkSuite) -> None:
        """Register a benchmark suite."""
        self._benchmarks[suite.suite_id] = suite

    def evaluate_output(
        self,
        output: str,
        task_description: str,
        agent_id: str,
        task_id: str = "",
        benchmark_type: BenchmarkType = BenchmarkType.GENERAL,
        token_usage: dict[str, int] | None = None,
        duration_ms: float = 0.0,
    ) -> EvalResult:
        """Evaluate agent output using rule-based heuristics."""
        start = time.monotonic()
        scores: list[EvalScore] = []

        # Completeness: does the output address the task?
        completeness = self._score_completeness(output, task_description)
        scores.append(completeness)

        # Code quality: if output contains code
        if self._looks_like_code(output):
            code_quality = self._score_code_quality(output)
            scores.append(code_quality)

        # Readability
        readability = self._score_readability(output)
        scores.append(readability)

        eval_duration = (time.monotonic() - start) * 1000
        result = EvalResult(
            task_id=task_id,
            agent_id=agent_id,
            scores=scores,
            benchmark_type=benchmark_type,
            duration_ms=duration_ms or eval_duration,
            token_usage=token_usage or {},
        )
        result.compute_overall()
        result.passed = result.overall_score >= self.pass_threshold
        result.feedback = self._generate_feedback(result)

        self.logger.log(result)
        return result

    def _score_completeness(self, output: str, task: str) -> EvalScore:
        """Score how completely the output addresses the task."""
        if not output.strip():
            return EvalScore(
                dimension=EvalDimension.COMPLETENESS,
                score=0.0,
                details="Empty output",
            )

        score = min(1.0, len(output.strip()) / max(100, len(task)))

        task_words = set(task.lower().split())
        output_words = set(output.lower().split())
        overlap = len(task_words & output_words) / max(1, len(task_words))
        score = (score + overlap) / 2

        return EvalScore(
            dimension=EvalDimension.COMPLETENESS,
            score=round(score, 3),
            weight=1.5,
            details=f"Length ratio + keyword overlap: {overlap:.2f}",
        )

    def _score_code_quality(self, output: str) -> EvalScore:
        """Basic code quality heuristics."""
        score = 0.7  # baseline
        issues: list[str] = []

        if "TODO" in output or "FIXME" in output:
            score -= 0.1
            issues.append("Contains TODO/FIXME markers")
        if "import *" in output:
            score -= 0.15
            issues.append("Uses wildcard imports")
        if "except:" in output and "except Exception" not in output:
            score -= 0.1
            issues.append("Bare except clause")
        if "eval(" in output:
            score -= 0.2
            issues.append("Uses eval()")
        if "print(" in output and "logger" not in output:
            score -= 0.05
            issues.append("Uses print() instead of logger")

        lines = output.split("\n")
        long_lines = sum(1 for line in lines if len(line) > 120)
        if long_lines > 3:
            score -= 0.1
            issues.append(f"{long_lines} lines exceed 120 chars")

        return EvalScore(
            dimension=EvalDimension.CODE_QUALITY,
            score=max(0.0, round(score, 3)),
            weight=1.2,
            details="; ".join(issues) if issues else "Clean code",
        )

    def _score_readability(self, output: str) -> EvalScore:
        """Score output readability."""
        if not output.strip():
            return EvalScore(dimension=EvalDimension.READABILITY, score=0.0)

        lines = output.split("\n")
        avg_line_len = sum(len(line) for line in lines) / max(1, len(lines))

        score = 0.8
        if avg_line_len > 100:
            score -= 0.2
        if len(lines) == 1 and len(output) > 200:
            score -= 0.2

        return EvalScore(
            dimension=EvalDimension.READABILITY,
            score=max(0.0, round(score, 3)),
            weight=0.8,
            details=f"Avg line length: {avg_line_len:.0f}",
        )

    def _looks_like_code(self, output: str) -> bool:
        """Heuristic check if output contains code."""
        code_indicators = ["def ", "class ", "import ", "function ", "const ", "var ", "let "]
        return any(ind in output for ind in code_indicators)

    def _generate_feedback(self, result: EvalResult) -> str:
        """Generate human-readable feedback from scores."""
        parts: list[str] = []
        if result.passed:
            parts.append(f"Score: {result.overall_score:.2f} (PASSED)")
        else:
            parts.append(f"Score: {result.overall_score:.2f} (BELOW THRESHOLD {self.pass_threshold})")

        for score in result.scores:
            if score.score < 0.5:
                parts.append(f"  ⚠ {score.dimension.value}: {score.score:.2f} — {score.details}")
        return "\n".join(parts)
