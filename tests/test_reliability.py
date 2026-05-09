"""Tests for Group 2: Reliability & Production-grade modules.

Covers HITL approval gates, self-evaluation, error recovery,
and observability/tracing.
"""

from __future__ import annotations

import tempfile
from unittest.mock import MagicMock

import pytest

from nexus.core.agent import AgentRole
from nexus.core.evaluation import (
    BenchmarkCase,
    BenchmarkSuite,
    BenchmarkType,
    EvalDimension,
    EvalResult,
    EvalScore,
    MetricsLogger,
    SelfEvaluator,
)
from nexus.core.hitl import (
    ApprovalGateManager,
    ApprovalRequest,
    ApprovalStatus,
    DiffPreview,
    GatePolicy,
    GateType,
    SensitivityLevel,
)
from nexus.core.message import Message, MessageType
from nexus.core.observability import (
    AgentMetrics,
    CostTracker,
    Span,
    SpanKind,
    Trace,
    Tracer,
    TraceStore,
)
from nexus.core.recovery import (
    ErrorClassifier,
    FailureType,
    RecoveryAction,
    RecoveryManager,
    ReflectionEngine,
    RetryPolicy,
)
from nexus.core.registry import AgentRegistry

# ── HITL / Approval Gates ──────────────────────────────────────────


class TestDiffPreview:
    def test_diff_generation(self) -> None:
        diff = DiffPreview(
            file_path="config.yaml",
            original="key: old_value\n",
            proposed="key: new_value\n",
        )
        assert diff.additions >= 1
        assert diff.deletions >= 1
        assert "old_value" in diff.diff_text
        assert "new_value" in diff.diff_text

    def test_sensitivity_auto_detect(self) -> None:
        diff = DiffPreview(
            file_path=".env.production",
            original="",
            proposed="SECRET=abc",
        )
        assert diff.sensitivity == SensitivityLevel.LOW  # not auto-set by DiffPreview

    def test_to_dict(self) -> None:
        diff = DiffPreview(
            file_path="test.py",
            original="a = 1\n",
            proposed="a = 2\n",
            sensitivity=SensitivityLevel.HIGH,
        )
        d = diff.to_dict()
        assert d["file_path"] == "test.py"
        assert d["sensitivity"] == "high"


class TestApprovalRequest:
    def test_approve(self) -> None:
        req = ApprovalRequest(description="Deploy to prod")
        req.approve(reviewer="admin", comment="LGTM")
        assert req.status == ApprovalStatus.APPROVED
        assert req.reviewer == "admin"
        assert req.resolved_at != ""

    def test_reject(self) -> None:
        req = ApprovalRequest(description="Delete DB")
        req.reject(reviewer="admin", comment="Too risky")
        assert req.status == ApprovalStatus.REJECTED

    def test_to_dict(self) -> None:
        req = ApprovalRequest(
            gate_type=GateType.DEPLOY,
            description="Deploy v2",
            sensitivity=SensitivityLevel.CRITICAL,
        )
        d = req.to_dict()
        assert d["gate_type"] == "deploy"
        assert d["sensitivity"] == "critical"
        assert d["status"] == "pending"


class TestGatePolicy:
    def test_requires_approval_above_threshold(self) -> None:
        policy = GatePolicy(
            gate_type=GateType.GIT_COMMIT,
            min_sensitivity=SensitivityLevel.MEDIUM,
        )
        assert not policy.requires_approval(SensitivityLevel.LOW)
        assert policy.requires_approval(SensitivityLevel.MEDIUM)
        assert policy.requires_approval(SensitivityLevel.HIGH)
        assert policy.requires_approval(SensitivityLevel.CRITICAL)

    def test_disabled_policy(self) -> None:
        policy = GatePolicy(
            gate_type=GateType.DEPLOY,
            enabled=False,
        )
        assert not policy.requires_approval(SensitivityLevel.CRITICAL)


class TestApprovalGateManager:
    def test_auto_approve_below_threshold(self) -> None:
        mgr = ApprovalGateManager()
        req = mgr.check_gate(
            GateType.FILE_WRITE,
            "Write to readme.md",
            sensitivity=SensitivityLevel.LOW,
        )
        assert req.status == ApprovalStatus.APPROVED

    def test_pending_above_threshold(self) -> None:
        mgr = ApprovalGateManager()
        req = mgr.check_gate(
            GateType.DEPLOY,
            "Deploy to production",
            sensitivity=SensitivityLevel.HIGH,
        )
        assert req.status == ApprovalStatus.PENDING
        assert len(mgr.pending_requests) == 1

    def test_resolve_pending(self) -> None:
        mgr = ApprovalGateManager()
        req = mgr.check_gate(
            GateType.DEPLOY,
            "Deploy",
            sensitivity=SensitivityLevel.HIGH,
        )
        resolved = mgr.resolve(req.request_id, approved=True, comment="Go ahead")
        assert resolved is not None
        assert resolved.status == ApprovalStatus.APPROVED
        assert len(mgr.pending_requests) == 0

    def test_resolve_nonexistent(self) -> None:
        mgr = ApprovalGateManager()
        assert mgr.resolve("nonexistent", approved=True) is None

    def test_auto_approve_mode(self) -> None:
        mgr = ApprovalGateManager(auto_approve=True)
        req = mgr.check_gate(
            GateType.DEPLOY,
            "Deploy",
            sensitivity=SensitivityLevel.CRITICAL,
        )
        assert req.status == ApprovalStatus.APPROVED

    def test_classify_sensitivity(self) -> None:
        mgr = ApprovalGateManager()
        assert mgr.classify_sensitivity(".env") == SensitivityLevel.CRITICAL
        assert mgr.classify_sensitivity("src/main.py") == SensitivityLevel.LOW
        assert mgr.classify_sensitivity("config.yaml") == SensitivityLevel.HIGH
        assert mgr.classify_sensitivity("pyproject.toml") == SensitivityLevel.MEDIUM

    def test_create_file_diff(self) -> None:
        mgr = ApprovalGateManager()
        diff = mgr.create_file_diff(".env", "OLD=1\n", "NEW=2\n")
        assert diff.sensitivity == SensitivityLevel.CRITICAL
        assert diff.additions >= 1

    def test_summary(self) -> None:
        mgr = ApprovalGateManager()
        mgr.check_gate(GateType.FILE_WRITE, "Write", sensitivity=SensitivityLevel.LOW)
        s = mgr.summary()
        assert s["total_reviewed"] >= 1
        assert "policies" in s

    def test_callback(self) -> None:
        callback = MagicMock()
        mgr = ApprovalGateManager()
        mgr.register_callback(callback)
        mgr.check_gate(GateType.DEPLOY, "Deploy", sensitivity=SensitivityLevel.HIGH)
        callback.assert_called_once()


# ── Self-Evaluation Framework ──────────────────────────────────────


class TestEvalScore:
    def test_weighted_score(self) -> None:
        score = EvalScore(
            dimension=EvalDimension.CORRECTNESS,
            score=0.8,
            weight=1.5,
        )
        assert score.weighted_score() == pytest.approx(1.2)


class TestEvalResult:
    def test_compute_overall(self) -> None:
        result = EvalResult(
            scores=[
                EvalScore(dimension=EvalDimension.COMPLETENESS, score=0.8, weight=1.0),
                EvalScore(dimension=EvalDimension.READABILITY, score=0.6, weight=1.0),
            ]
        )
        overall = result.compute_overall()
        assert overall == pytest.approx(0.7)

    def test_empty_scores(self) -> None:
        result = EvalResult()
        assert result.compute_overall() == 0.0

    def test_to_dict(self) -> None:
        result = EvalResult(
            agent_id="qa",
            benchmark_type=BenchmarkType.CODE_GEN,
        )
        d = result.to_dict()
        assert d["agent_id"] == "qa"
        assert d["benchmark_type"] == "code_gen"


class TestMetricsLogger:
    def test_log_and_retrieve(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = MetricsLogger(metrics_dir=tmpdir)
            result = EvalResult(agent_id="test", overall_score=0.85, passed=True)
            logger.log(result)
            entries = logger.get_entries()
            assert len(entries) == 1
            assert entries[0].agent_id == "test"

    def test_agent_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = MetricsLogger(metrics_dir=tmpdir)
            for score in [0.9, 0.7, 0.8]:
                r = EvalResult(agent_id="dev", overall_score=score, passed=score > 0.6)
                logger.log(r)
            stats = logger.agent_stats("dev")
            assert stats["total_evals"] == 3
            assert stats["avg_score"] == pytest.approx(0.8)
            assert stats["pass_rate"] == pytest.approx(1.0)

    def test_load_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = MetricsLogger(metrics_dir=tmpdir)
            logger.log(EvalResult(agent_id="x", overall_score=0.5))
            history = logger.load_history()
            assert len(history) == 1
            assert history[0]["agent_id"] == "x"

    def test_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = MetricsLogger(metrics_dir=tmpdir)
            logger.log(EvalResult(agent_id="a", overall_score=0.9, passed=True))
            logger.log(EvalResult(agent_id="b", overall_score=0.3, passed=False))
            s = logger.summary()
            assert s["total_evals"] == 2
            assert "a" in s["agents"]
            assert "b" in s["agents"]


class TestSelfEvaluator:
    def test_evaluate_code_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = SelfEvaluator(
                metrics_logger=MetricsLogger(metrics_dir=tmpdir),
            )
            result = evaluator.evaluate_output(
                output="def hello():\n    return 'Hello World'\n",
                task_description="Write a hello function",
                agent_id="developer",
            )
            assert result.overall_score > 0
            assert len(result.scores) >= 2  # completeness + code_quality + readability

    def test_evaluate_empty_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = SelfEvaluator(
                metrics_logger=MetricsLogger(metrics_dir=tmpdir),
            )
            result = evaluator.evaluate_output(
                output="",
                task_description="Do something",
                agent_id="test",
            )
            assert result.overall_score == 0.0
            assert not result.passed

    def test_code_quality_penalties(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = SelfEvaluator(
                metrics_logger=MetricsLogger(metrics_dir=tmpdir),
            )
            bad_code = "from module import *\ndef f():\n    eval('x')\n    except:\n        pass\n"
            result = evaluator.evaluate_output(
                output=bad_code,
                task_description="Write code",
                agent_id="dev",
            )
            code_scores = [s for s in result.scores if s.dimension == EvalDimension.CODE_QUALITY]
            assert len(code_scores) == 1
            assert code_scores[0].score < 0.7

    def test_register_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = SelfEvaluator(
                metrics_logger=MetricsLogger(metrics_dir=tmpdir),
            )
            suite = BenchmarkSuite(
                suite_id="test-suite",
                name="Test Suite",
                benchmark_type=BenchmarkType.CODE_GEN,
            )
            suite.add_case(
                BenchmarkCase(
                    case_id="case-1",
                    description="Hello world",
                    input_data="print hello",
                )
            )
            evaluator.register_benchmark(suite)
            assert "test-suite" in evaluator._benchmarks


# ── Error Recovery ─────────────────────────────────────────────────


class TestErrorClassifier:
    def test_classify_timeout(self) -> None:
        assert ErrorClassifier.classify("Request timed out") == FailureType.TIMEOUT

    def test_classify_llm_error(self) -> None:
        assert ErrorClassifier.classify("API error: rate limit") == FailureType.LLM_ERROR

    def test_classify_invalid_output(self) -> None:
        assert ErrorClassifier.classify("JSON parse error") == FailureType.INVALID_OUTPUT

    def test_classify_tool_failure(self) -> None:
        assert ErrorClassifier.classify("Tool execution failed") == FailureType.TOOL_FAILURE

    def test_classify_unknown(self) -> None:
        assert ErrorClassifier.classify("Something weird") == FailureType.UNKNOWN


class TestRetryPolicy:
    def test_retryable(self) -> None:
        policy = RetryPolicy()
        assert policy.is_retryable(FailureType.LLM_ERROR)
        assert policy.is_retryable(FailureType.TIMEOUT)
        assert not policy.is_retryable(FailureType.VALIDATION_ERROR)

    def test_delay_backoff(self) -> None:
        policy = RetryPolicy(base_delay_ms=100, backoff_factor=2.0)
        assert policy.delay_ms(0) == 100
        assert policy.delay_ms(1) == 200
        assert policy.delay_ms(2) == 400

    def test_max_delay(self) -> None:
        policy = RetryPolicy(base_delay_ms=1000, max_delay_ms=5000, backoff_factor=10)
        assert policy.delay_ms(5) == 5000


class TestReflectionEngine:
    def test_layer_1(self) -> None:
        engine = ReflectionEngine()
        prompt = engine.generate_reflection_prompt(
            "Write tests",
            "Tests failed with import error",
            attempt_number=1,
        )
        assert "DIAGNOSE" in prompt
        assert "import error" in prompt

    def test_layer_2(self) -> None:
        engine = ReflectionEngine()
        prompt = engine.generate_reflection_prompt(
            "Write tests",
            "Tests still failing",
            attempt_number=2,
        )
        assert "STRATEGY" in prompt

    def test_layer_3(self) -> None:
        engine = ReflectionEngine()
        prompt = engine.generate_reflection_prompt(
            "Write tests",
            "Tests still failing",
            attempt_number=3,
            previous_reflections=["First attempt failed", "Second attempt failed"],
        )
        assert "VERIFY" in prompt
        assert "First attempt failed" in prompt


class TestRecoveryManager:
    def _make_registry(self) -> AgentRegistry:
        """Create a registry with a mock agent."""
        registry = AgentRegistry()
        agent = MagicMock()
        agent.agent_id = "test_agent"
        agent.role = AgentRole.DEBUGGER
        agent.process.return_value = Message(
            sender="test_agent",
            recipient="orchestrator",
            type=MessageType.TASK_RESULT,
            payload={"status": "complete", "result": "Fixed!"},
        )
        registry.register(agent)
        return registry

    def test_retry_success(self) -> None:
        registry = self._make_registry()
        # Fail first, succeed on retry
        agent = registry.get("test_agent")
        assert agent is not None
        agent.process.side_effect = [
            Exception("Timeout error"),
            Message(
                sender="test_agent",
                recipient="orchestrator",
                type=MessageType.TASK_RESULT,
                payload={"status": "complete", "result": "OK"},
            ),
        ]
        mgr = RecoveryManager(
            registry,
            retry_policy=RetryPolicy(max_retries=2, base_delay_ms=1),
        )
        msg = Message(
            sender="user",
            recipient="test_agent",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Fix bug"},
        )
        result = mgr.recover("test_agent", msg, "Timeout error")
        assert result.recovered
        assert result.final_action == RecoveryAction.RETRY

    def test_all_retries_fail_then_reflect(self) -> None:
        registry = self._make_registry()
        agent = registry.get("test_agent")
        assert agent is not None
        # Fail on all retries, succeed on reflection
        agent.process.side_effect = [
            Exception("Timeout error"),
            Exception("Timeout error"),
            Exception("Timeout error"),
            Message(
                sender="test_agent",
                recipient="orchestrator",
                type=MessageType.TASK_RESULT,
                payload={"status": "complete", "result": "Reflected!"},
            ),
        ]
        mgr = RecoveryManager(
            registry,
            retry_policy=RetryPolicy(max_retries=3, base_delay_ms=1),
        )
        msg = Message(
            sender="user",
            recipient="test_agent",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Fix bug"},
        )
        result = mgr.recover("test_agent", msg, "Timeout error")
        assert result.recovered
        assert result.final_action == RecoveryAction.REFLECT

    def test_escalation_when_all_fails(self) -> None:
        registry = self._make_registry()
        agent = registry.get("test_agent")
        assert agent is not None
        agent.process.side_effect = Exception("Always fails")
        mgr = RecoveryManager(
            registry,
            retry_policy=RetryPolicy(max_retries=1, base_delay_ms=1),
        )
        msg = Message(
            sender="user",
            recipient="test_agent",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Impossible task"},
        )
        result = mgr.recover("test_agent", msg, "Timeout error")
        assert not result.recovered
        assert result.final_action == RecoveryAction.ESCALATE

    def test_non_retryable_skips_retry(self) -> None:
        registry = self._make_registry()
        agent = registry.get("test_agent")
        assert agent is not None
        # Return None on reflection to force escalation
        agent.process.return_value = None
        mgr = RecoveryManager(
            registry,
            retry_policy=RetryPolicy(max_retries=3, base_delay_ms=1),
        )
        msg = Message(
            sender="user",
            recipient="test_agent",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Validate schema"},
        )
        # Validation error is not retryable by default
        result = mgr.recover("test_agent", msg, "Validation error: field missing")
        assert not result.recovered

    def test_summary(self) -> None:
        registry = self._make_registry()
        mgr = RecoveryManager(
            registry,
            retry_policy=RetryPolicy(max_retries=1, base_delay_ms=1),
        )
        msg = Message(
            sender="user",
            recipient="test_agent",
            type=MessageType.TASK_REQUEST,
            payload={"task": "Test"},
        )
        mgr.recover("test_agent", msg, "Error")
        s = mgr.summary()
        assert s["total_recoveries"] >= 1


# ── Observability & Tracing ────────────────────────────────────────


class TestSpan:
    def test_finish(self) -> None:
        span = Span(name="test", start_time=0.0)
        span.finish(status="ok")
        assert span.duration_ms > 0
        assert span.status == "ok"

    def test_to_dict(self) -> None:
        span = Span(name="test", kind=SpanKind.LLM_CALL, agent_id="dev")
        d = span.to_dict()
        assert d["kind"] == "llm_call"
        assert d["agent_id"] == "dev"


class TestTrace:
    def test_add_span(self) -> None:
        trace = Trace(task="Build login")
        span = Span(name="agent_call")
        trace.add_span(span)
        assert len(trace.spans) == 1
        assert span.trace_id == trace.trace_id

    def test_finish_aggregates_tokens(self) -> None:
        import time

        trace = Trace(task="Test", start_time=time.monotonic())
        s1 = Span(name="s1", token_usage={"prompt_tokens": 100, "completion_tokens": 50})
        s2 = Span(name="s2", token_usage={"prompt_tokens": 200, "completion_tokens": 100})
        trace.add_span(s1)
        trace.add_span(s2)
        trace.finish()
        assert trace.total_tokens["prompt_tokens"] == 300
        assert trace.total_tokens["completion_tokens"] == 150


class TestCostTracker:
    def test_estimate(self) -> None:
        tracker = CostTracker()
        estimate = tracker.estimate(
            model="deepseek-ai/deepseek-v4-pro",
            input_tokens=1000,
            output_tokens=500,
        )
        assert estimate.total_cost_usd > 0
        assert estimate.total_tokens == 1500

    def test_default_model(self) -> None:
        tracker = CostTracker()
        estimate = tracker.estimate(
            model="unknown-model",
            input_tokens=1000,
            output_tokens=500,
        )
        assert estimate.total_cost_usd > 0

    def test_summary(self) -> None:
        tracker = CostTracker()
        tracker.estimate("deepseek-ai/deepseek-v4-pro", 1000, 500)
        tracker.estimate("deepseek-ai/deepseek-v4-flash", 2000, 1000)
        s = tracker.summary()
        assert s["total_calls"] == 2
        assert s["total_cost_usd"] > 0
        assert len(s["by_model"]) == 2


class TestAgentMetrics:
    def test_record_and_get_stats(self) -> None:
        metrics = AgentMetrics()
        metrics.record_call("dev", 100.0, tokens=500, success=True)
        metrics.record_call("dev", 200.0, tokens=600, success=True)
        metrics.record_call("dev", 150.0, tokens=0, success=False)
        stats = metrics.get_stats("dev")
        assert stats["calls"] == 3
        assert stats["errors"] == 1
        assert stats["error_rate"] == pytest.approx(1 / 3)
        assert stats["total_tokens"] == 1100
        assert stats["avg_latency_ms"] == pytest.approx(150.0)

    def test_unknown_agent(self) -> None:
        metrics = AgentMetrics()
        stats = metrics.get_stats("nonexistent")
        assert stats["calls"] == 0


class TestTraceStore:
    def test_store_and_retrieve(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TraceStore(metrics_dir=tmpdir)
            trace = Trace(task="Test task")
            store.store(trace)
            assert len(store.recent()) == 1
            assert store.get_trace(trace.trace_id) is not None

    def test_load_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TraceStore(metrics_dir=tmpdir)
            store.store(Trace(task="Task 1"))
            store.store(Trace(task="Task 2"))
            history = store.load_history()
            assert len(history) == 2


class TestTracer:
    def test_full_trace_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tracer = Tracer(trace_store=TraceStore(metrics_dir=tmpdir))
            trace = tracer.start_trace("Build login page")
            span = tracer.start_span(
                trace,
                SpanKind.AGENT_CALL,
                "orchestrator",
                agent_id="orchestrator",
            )
            tracer.finish_span(span, status="ok")
            tracer.finish_trace(trace, status="ok")
            assert trace.status == "ok"
            assert len(trace.spans) == 1

    def test_span_with_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tracer = Tracer(trace_store=TraceStore(metrics_dir=tmpdir))
            trace = tracer.start_trace("Test")
            span = tracer.start_span(
                trace,
                SpanKind.LLM_CALL,
                "llm_call",
                agent_id="dev",
                model="deepseek-ai/deepseek-v4-pro",
            )
            tracer.finish_span(
                span,
                token_usage={"prompt_tokens": 100, "completion_tokens": 50},
            )
            tracer.finish_trace(trace)
            assert tracer.costs.total_cost() > 0
            stats = tracer.metrics.get_stats("dev")
            assert stats["total_tokens"] == 150

    def test_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tracer = Tracer(trace_store=TraceStore(metrics_dir=tmpdir))
            s = tracer.summary()
            assert s["active_traces"] == 0
            assert s["total_traces"] == 0


# ── Sandbox fix verification ──────────────────────────────────────


class TestSandboxRegex:
    def test_blocks_rm_rf_root(self) -> None:
        from nexus.mcp.sandbox import Sandbox, SandboxError

        sb = Sandbox()
        with pytest.raises(SandboxError):
            sb.validate_command("rm -rf /")

    def test_blocks_rm_rf_star(self) -> None:
        from nexus.mcp.sandbox import Sandbox, SandboxError

        sb = Sandbox()
        with pytest.raises(SandboxError):
            sb.validate_command("rm -rf /*")

    def test_allows_rm_rf_subpath(self) -> None:
        from nexus.mcp.sandbox import Sandbox

        sb = Sandbox()
        sb.validate_command("rm -rf /tmp/build")  # should NOT raise

    def test_allows_rm_rf_relative(self) -> None:
        from nexus.mcp.sandbox import Sandbox

        sb = Sandbox()
        sb.validate_command("rm -rf ./dist")  # should NOT raise

    def test_blocks_fork_bomb(self) -> None:
        from nexus.mcp.sandbox import Sandbox, SandboxError

        sb = Sandbox()
        with pytest.raises(SandboxError):
            sb.validate_command(":(){ :|:& };:")

    def test_blocks_shutdown(self) -> None:
        from nexus.mcp.sandbox import Sandbox, SandboxError

        sb = Sandbox()
        with pytest.raises(SandboxError):
            sb.validate_command("shutdown -h now")

    def test_blocks_chmod_root(self) -> None:
        from nexus.mcp.sandbox import Sandbox, SandboxError

        sb = Sandbox()
        with pytest.raises(SandboxError):
            sb.validate_command("chmod -R 777 /")

    def test_allows_chmod_subpath(self) -> None:
        from nexus.mcp.sandbox import Sandbox

        sb = Sandbox()
        sb.validate_command("chmod -R 777 /var/www/html")  # should NOT raise


# ── Workflow design-skip fix verification ──────────────────────────


class TestWorkflowDesignSkip:
    def test_skips_design_when_no_design_keywords(self) -> None:
        from nexus.core.workflow import PhaseResult, WorkflowEngine, WorkflowGraph, WorkflowPhase

        registry = AgentRegistry()
        graph = WorkflowGraph.create_default()
        engine = WorkflowEngine(registry=registry, graph=graph)

        # Simulate PLAN phase output without design keywords
        plan_result = PhaseResult(
            phase=WorkflowPhase.PLAN,
            outputs=[{"result": "Build a REST API with authentication"}],
        )
        next_phase = engine._decide_next_phase(WorkflowPhase.PLAN, plan_result)
        assert next_phase == WorkflowPhase.CODE

    def test_goes_to_design_when_design_keywords_present(self) -> None:
        from nexus.core.workflow import PhaseResult, WorkflowEngine, WorkflowGraph, WorkflowPhase

        registry = AgentRegistry()
        graph = WorkflowGraph.create_default()
        engine = WorkflowEngine(registry=registry, graph=graph)

        # Simulate PLAN phase output with design keywords
        plan_result = PhaseResult(
            phase=WorkflowPhase.PLAN,
            outputs=[{"result": "Design the UI with wireframes and mockup"}],
        )
        next_phase = engine._decide_next_phase(WorkflowPhase.PLAN, plan_result)
        assert next_phase == WorkflowPhase.DESIGN


# ── Integration: team.py has new components ────────────────────────


class TestTeamReliabilityIntegration:
    def test_team_has_approval_gates(self) -> None:
        from nexus.team import NexusTeam

        team = NexusTeam()
        assert team.approval_gates is not None
        assert team.approval_gates.summary()["pending"] == 0

    def test_team_has_evaluator(self) -> None:
        from nexus.team import NexusTeam

        team = NexusTeam()
        assert team.evaluator is not None

    def test_team_has_tracer(self) -> None:
        from nexus.team import NexusTeam

        team = NexusTeam()
        assert team.tracer is not None
        assert team.tracer.summary()["total_traces"] == 0

    def test_team_has_recovery(self) -> None:
        from nexus.team import NexusTeam

        team = NexusTeam()
        assert team.recovery is not None

    def test_run_returns_evaluation(self) -> None:
        from nexus.team import NexusTeam

        team = NexusTeam()
        result = team.run("Build a React login component")
        assert "evaluation" in result
        assert "score" in result["evaluation"]
        assert "passed" in result["evaluation"]

    def test_run_returns_trace_id(self) -> None:
        from nexus.team import NexusTeam

        team = NexusTeam()
        result = team.run("Hello world")
        assert "trace_id" in result
        assert len(result["trace_id"]) > 0
