"""Tests for temporal evaluator module."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from arf_rt.temporal.evaluator import TemporalEvaluator, EvaluationStats
from arf_rt.temporal.config import TemporalConfig
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.verdict import VerdictKind


class TestTemporalEvaluatorBasic:
    """Tests for basic evaluator functionality."""

    def test_default_config(self):
        """Test evaluator with default config."""
        evaluator = TemporalEvaluator()
        assert evaluator.config is not None
        assert isinstance(evaluator.config, TemporalConfig)

    def test_custom_config(self):
        """Test evaluator with custom config."""
        config = TemporalConfig(min_hop_delta_seconds=0.1)
        evaluator = TemporalEvaluator(config=config)
        assert evaluator.config.min_hop_delta_seconds == 0.1

    def test_custom_reference_time(self):
        """Test evaluator with custom reference time."""
        ref = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        evaluator = TemporalEvaluator(reference_time=ref)
        assert evaluator.reference_time == ref

    def test_stats_disabled_by_default(self):
        """Test stats are disabled by default."""
        evaluator = TemporalEvaluator()
        assert evaluator.stats is None


class TestEvaluationStats:
    """Tests for EvaluationStats."""

    def test_initial_state(self):
        """Test initial stats state."""
        stats = EvaluationStats()
        assert stats.constraints_evaluated == 0
        assert stats.constraints_passed == 0
        assert stats.constraints_failed == 0
        assert stats.constraints_unknown == 0
        assert stats.evaluation_time_ms == 0.0
        assert stats.path_length == 0
        assert stats.missing_constraints == set()

    def test_to_dict(self):
        """Test stats serialization."""
        stats = EvaluationStats()
        stats.constraints_evaluated = 5
        stats.constraints_passed = 3
        stats.constraints_failed = 1
        stats.constraints_unknown = 1
        stats.evaluation_time_ms = 1.5
        stats.path_length = 4
        stats.missing_constraints = {"TC-2", "TC-4"}

        d = stats.to_dict()
        assert d["constraints_evaluated"] == 5
        assert d["constraints_passed"] == 3
        assert d["constraints_failed"] == 1
        assert d["constraints_unknown"] == 1
        assert d["evaluation_time_ms"] == 1.5
        assert d["path_length"] == 4
        assert set(d["missing_constraints"]) == {"TC-2", "TC-4"}


class TestTemporalEvaluatorWithStats:
    """Tests for evaluator with stats enabled."""

    def test_stats_enabled(self):
        """Test stats collection when enabled."""
        evaluator = TemporalEvaluator(enable_stats=True)
        assert evaluator.stats is not None
        assert isinstance(evaluator.stats, EvaluationStats)

    def test_stats_collected_on_evaluate(self):
        """Test stats are collected during evaluation."""
        from datetime import datetime, timezone, timedelta

        evaluator = TemporalEvaluator(enable_stats=True)
        now = datetime.now(timezone.utc)

        hints = {
            "e1": TemporalHint(
                edge_id="e1",
                earliest_observed=now,
                latest_observed=now + timedelta(seconds=1),
                credential_issued=now,
                credential_expiry=now + timedelta(hours=1),
                last_used=now,
            ),
            "e2": TemporalHint(
                edge_id="e2",
                earliest_observed=now + timedelta(seconds=2),
                latest_observed=now + timedelta(seconds=3),
                credential_issued=now + timedelta(seconds=2),
                credential_expiry=now + timedelta(hours=1),
                last_used=now + timedelta(seconds=2),
            ),
        }

        verdict = evaluator.evaluate(["e1", "e2"], hints)

        assert evaluator.stats is not None
        assert evaluator.stats.constraints_evaluated > 0
        assert evaluator.stats.evaluation_time_ms >= 0
        assert evaluator.stats.path_length == 2

    def test_evaluate_with_metrics(self):
        """Test evaluate_with_metrics method."""
        from arf_rt.temporal.metrics import TemporalMetrics

        evaluator = TemporalEvaluator(enable_stats=True)
        now = datetime.now(timezone.utc)

        hints = {
            "e1": TemporalHint(
                edge_id="e1",
                earliest_observed=now,
                latest_observed=now + timedelta(seconds=1),
                credential_issued=now,
                credential_expiry=now + timedelta(hours=1),
                last_used=now,
            ),
        }

        metrics = TemporalMetrics()
        verdict = evaluator.evaluate_with_metrics(["e1"], hints, metrics)

        assert metrics.total_paths == 1
        if verdict.is_feasible():
            assert metrics.feasible_count == 1


class TestConstraintEvaluation:
    """Tests for individual constraint evaluation."""

    def test_tc1_causal_order_violation(self):
        """Test TC-1 causal order violation."""
        evaluator = TemporalEvaluator(enable_stats=True)
        now = datetime.now(timezone.utc)

        hints = {
            "e1": TemporalHint(
                edge_id="e1",
                earliest_observed=now + timedelta(seconds=10),
                latest_observed=now + timedelta(seconds=10),
            ),
            "e2": TemporalHint(
                edge_id="e2",
                earliest_observed=now,
                latest_observed=now,
            ),
        }

        verdict = evaluator.evaluate(["e1", "e2"], hints)
        assert verdict.is_infeasible()
        assert verdict.violated_constraint == "TC-1"

    def test_tc2_session_expiry(self):
        """Test TC-2 session expiry violation."""
        evaluator = TemporalEvaluator(
            config=TemporalConfig(session_expiry_grace_seconds=0),
            enable_stats=True,
        )
        now = datetime.now(timezone.utc)

        hints = {
            "e1": TemporalHint(
                edge_id="e1",
                earliest_observed=now,
                latest_observed=now + timedelta(seconds=1),
                credential_issued=now - timedelta(hours=2),
                credential_expiry=now - timedelta(hours=1),
            ),
            "e2": TemporalHint(
                edge_id="e2",
                earliest_observed=now + timedelta(seconds=2),
                latest_observed=now + timedelta(seconds=3),
                credential_issued=now,
                credential_expiry=now + timedelta(hours=1),
            ),
        }

        verdict = evaluator.evaluate(["e1", "e2"], hints)
        assert verdict.is_infeasible()
        assert verdict.violated_constraint == "TC-2"

    def test_tc3_min_velocity(self):
        """Test TC-3 minimum velocity violation."""
        evaluator = TemporalEvaluator(
            config=TemporalConfig(min_hop_delta_seconds=1.0),
            enable_stats=True,
        )
        now = datetime.now(timezone.utc)

        hints = {
            "e1": TemporalHint(
                edge_id="e1",
                earliest_observed=now,
                latest_observed=now + timedelta(seconds=0.1),
            ),
            "e2": TemporalHint(
                edge_id="e2",
                earliest_observed=now + timedelta(seconds=0.2),
                latest_observed=now + timedelta(seconds=0.3),
            ),
        }

        verdict = evaluator.evaluate(["e1", "e2"], hints)
        assert verdict.is_infeasible()
        assert verdict.violated_constraint == "TC-3"

    def test_tc4_stale_credential(self):
        """Test TC-4 stale credential violation."""
        evaluator = TemporalEvaluator(
            config=TemporalConfig(stale_credential_days=30),
            reference_time=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            enable_stats=True,
        )

        hints = {
            "e1": TemporalHint(
                edge_id="e1",
                earliest_observed=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                latest_observed=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                last_used=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            ),
        }

        verdict = evaluator.evaluate(["e1"], hints)
        assert verdict.is_infeasible()
        assert verdict.violated_constraint == "TC-4"

    def test_tc5_concurrent_session(self):
        """Test TC-5 concurrent session detection."""
        evaluator = TemporalEvaluator(enable_stats=True)
        now = datetime.now(timezone.utc)

        hints = {
            "e1": TemporalHint(
                edge_id="e1",
                earliest_observed=now,
                latest_observed=now + timedelta(seconds=1),
                credential_issued=now,
            ),
            "e2": TemporalHint(
                edge_id="e2",
                earliest_observed=now + timedelta(seconds=2),
                latest_observed=now + timedelta(seconds=3),
                credential_issued=now,  # Same credential_issued!
            ),
        }

        verdict = evaluator.evaluate(["e1", "e2"], hints)
        assert verdict.is_infeasible()
        assert verdict.violated_constraint == "TC-5"

    def test_unknown_when_data_missing(self):
        """Test UNKNOWN verdict when required data is missing."""
        evaluator = TemporalEvaluator(
            config=TemporalConfig(unknown_passthrough=True),
            enable_stats=True,
        )
        now = datetime.now(timezone.utc)

        hints = {
            "e1": TemporalHint(edge_id="e1"),
            "e2": TemporalHint(edge_id="e2"),
        }

        verdict = evaluator.evaluate(["e1", "e2"], hints)
        assert verdict.is_unknown()
        assert "TC-1" in verdict.missing_data_constraints

    def test_feasible_when_all_pass(self):
        """Test FEASIBLE when all constraints pass."""
        evaluator = TemporalEvaluator(enable_stats=True)
        now = datetime.now(timezone.utc)

        hints = {
            "e1": TemporalHint(
                edge_id="e1",
                earliest_observed=now,
                latest_observed=now + timedelta(seconds=1),
                credential_issued=now,
                credential_expiry=now + timedelta(hours=1),
                last_used=now,
            ),
            "e2": TemporalHint(
                edge_id="e2",
                earliest_observed=now + timedelta(seconds=2),
                latest_observed=now + timedelta(seconds=3),
                credential_issued=now + timedelta(seconds=2),
                credential_expiry=now + timedelta(hours=1),
                last_used=now + timedelta(seconds=2),
            ),
        }

        verdict = evaluator.evaluate(["e1", "e2"], hints)
        assert verdict.is_feasible()


class TestShortCircuitEvaluation:
    """Tests for short-circuit evaluation behavior."""

    def test_short_circuits_on_first_failure(self):
        """Test evaluation stops at first infeasible constraint."""
        evaluator = TemporalEvaluator(
            config=TemporalConfig(
                min_hop_delta_seconds=1.0,
                stale_credential_days=30,
            ),
            enable_stats=True,
        )
        now = datetime.now(timezone.utc)

        hints = {
            "e1": TemporalHint(
                edge_id="e1",
                earliest_observed=now,
                latest_observed=now + timedelta(seconds=0.1),  # TC-3 violation
                credential_issued=now - timedelta(days=100),  # Would also violate TC-4
                credential_expiry=now + timedelta(hours=1),
                last_used=now - timedelta(days=100),
            ),
            "e2": TemporalHint(
                edge_id="e2",
                earliest_observed=now + timedelta(seconds=0.2),
                latest_observed=now + timedelta(seconds=0.3),
                credential_issued=now,
                credential_expiry=now + timedelta(hours=1),
                last_used=now,
            ),
        }

        verdict = evaluator.evaluate(["e1", "e2"], hints)
        # Should fail on TC-3 first (checked before TC-4 for e1)
        assert verdict.is_infeasible()
        assert verdict.violated_constraint == "TC-3"


class TestConfigurableConstraints:
    """Tests for enabling/disabling constraints."""

    def test_disable_tc1(self):
        """Test disabling TC-1."""
        evaluator = TemporalEvaluator(
            config=TemporalConfig(enabled_constraints=["TC-2", "TC-3", "TC-4", "TC-5"]),
            enable_stats=True,
        )
        now = datetime.now(timezone.utc)

        hints = {
            "e1": TemporalHint(
                edge_id="e1",
                earliest_observed=now + timedelta(seconds=10),
                latest_observed=now + timedelta(seconds=10),
            ),
            "e2": TemporalHint(
                edge_id="e2",
                earliest_observed=now,
                latest_observed=now,
            ),
        }

        verdict = evaluator.evaluate(["e1", "e2"], hints)
        # TC-1 is disabled, should not fail
        assert not verdict.is_infeasible() or verdict.violated_constraint != "TC-1"