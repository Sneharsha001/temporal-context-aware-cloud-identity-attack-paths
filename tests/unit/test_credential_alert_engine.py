"""
tests/unit/test_credential_alert_engine.py - Unit tests for CredentialAlertEngine.

Validates rule evaluation, alert deduplication, severity grouping,
default rule coverage, and single-result convenience API.
"""

from __future__ import annotations

import pytest

from arf_rt.temporal.credential_alert_engine import (
    Alert,
    AlertRule,
    AlertSeverity,
    CredentialAlertEngine,
    DEFAULT_RULES,
)
from arf_rt.temporal.credential_scorer import CredentialRiskScore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score(
    edge_id: str = "e1",
    score: float = 0.50,
    expiry_factor: float = 0.5,
    staleness_factor: float = 0.5,
    short_lived_bonus: float = 0.0,
) -> CredentialRiskScore:
    return CredentialRiskScore(
        edge_id=edge_id,
        score=score,
        expiry_factor=expiry_factor,
        staleness_factor=staleness_factor,
        short_lived_bonus=short_lived_bonus,
    )


def _expired_score(edge_id: str = "expired-edge") -> CredentialRiskScore:
    return CredentialRiskScore(
        edge_id=edge_id,
        score=0.85,
        expiry_factor=1.0,
        staleness_factor=0.5,
        short_lived_bonus=0.0,
    )


# ---------------------------------------------------------------------------
# Alert dataclass
# ---------------------------------------------------------------------------

class TestAlert:
    def test_to_dict_has_required_keys(self):
        engine = CredentialAlertEngine()
        alerts = engine.evaluate([_expired_score()])
        assert alerts
        d = alerts[0].to_dict()
        for key in ("edge_id", "severity", "rule_name", "message", "score", "triggered_at"):
            assert key in d

    def test_to_dict_severity_is_string(self):
        engine = CredentialAlertEngine()
        alerts = engine.evaluate([_expired_score()])
        d = alerts[0].to_dict()
        assert isinstance(d["severity"], str)


# ---------------------------------------------------------------------------
# AlertRule
# ---------------------------------------------------------------------------

class TestAlertRule:
    def test_predicate_true_returns_alert(self):
        rule = AlertRule(
            name="TEST_RULE",
            severity=AlertSeverity.HIGH,
            predicate=lambda r: r.score > 0.5,
            message_template="edge {edge_id} score {score}",
        )
        result = rule.evaluate(_score(score=0.75))
        assert result is not None
        assert result.rule_name == "TEST_RULE"

    def test_predicate_false_returns_none(self):
        rule = AlertRule(
            name="TEST_RULE",
            severity=AlertSeverity.LOW,
            predicate=lambda r: r.score > 0.9,
            message_template="edge {edge_id}",
        )
        assert rule.evaluate(_score(score=0.5)) is None

    def test_message_template_interpolated(self):
        rule = AlertRule(
            name="DEMO",
            severity=AlertSeverity.MEDIUM,
            predicate=lambda r: True,
            message_template="Edge {edge_id} has score {score}",
        )
        alert = rule.evaluate(_score(edge_id="my-edge", score=0.42))
        assert "my-edge" in alert.message
        assert "0.42" in alert.message


# ---------------------------------------------------------------------------
# CredentialAlertEngine - basic evaluation
# ---------------------------------------------------------------------------

class TestEngineEvaluation:
    def test_no_alerts_below_threshold(self):
        engine = CredentialAlertEngine()
        alerts = engine.evaluate([_score(score=0.10, expiry_factor=0.1, staleness_factor=0.1)])
        assert alerts == []

    def test_critical_score_triggers_alert(self):
        engine = CredentialAlertEngine()
        alerts = engine.evaluate([_score(score=0.90)])
        names = [a.rule_name for a in alerts]
        assert "CRITICAL_SCORE" in names

    def test_high_score_triggers_alert(self):
        engine = CredentialAlertEngine()
        alerts = engine.evaluate([_score(score=0.70)])
        names = [a.rule_name for a in alerts]
        assert "HIGH_SCORE" in names

    def test_expired_credential_triggers_alert(self):
        engine = CredentialAlertEngine()
        alerts = engine.evaluate([_expired_score()])
        names = [a.rule_name for a in alerts]
        assert "EXPIRED_CREDENTIAL" in names

    def test_highly_stale_triggers_alert(self):
        engine = CredentialAlertEngine()
        alerts = engine.evaluate([_score(score=0.50, staleness_factor=0.95)])
        names = [a.rule_name for a in alerts]
        assert "HIGHLY_STALE" in names

    def test_multiple_results_all_evaluated(self):
        engine = CredentialAlertEngine()
        results = [
            _score("a", score=0.85),
            _score("b", score=0.10, staleness_factor=0.1, expiry_factor=0.1),
            _score("c", score=0.65),
        ]
        alerts = engine.evaluate(results)
        edge_ids = {a.edge_id for a in alerts}
        assert "a" in edge_ids
        assert "c" in edge_ids
        assert "b" not in edge_ids

    def test_empty_results_returns_empty(self):
        engine = CredentialAlertEngine()
        assert engine.evaluate([]) == []


# ---------------------------------------------------------------------------
# CredentialAlertEngine - deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_duplicate_alert_suppressed(self):
        engine = CredentialAlertEngine(deduplicate=True)
        result = _score(score=0.85)
        first = engine.evaluate([result])
        second = engine.evaluate([result])
        assert len(second) == 0  # all duplicates suppressed

    def test_reset_clears_dedup_state(self):
        engine = CredentialAlertEngine(deduplicate=True)
        result = _score(score=0.85)
        engine.evaluate([result])
        engine.reset()
        second = engine.evaluate([result])
        assert len(second) > 0

    def test_no_dedup_when_disabled(self):
        engine = CredentialAlertEngine(deduplicate=False)
        result = _score(score=0.85)
        first = engine.evaluate([result])
        second = engine.evaluate([result])
        assert len(second) == len(first)


# ---------------------------------------------------------------------------
# CredentialAlertEngine - evaluate_single
# ---------------------------------------------------------------------------

class TestEvaluateSingle:
    def test_single_critical_returns_alerts(self):
        engine = CredentialAlertEngine()
        alerts = engine.evaluate_single(_score(score=0.85))
        assert len(alerts) > 0

    def test_single_safe_returns_empty(self):
        engine = CredentialAlertEngine()
        alerts = engine.evaluate_single(_score(score=0.05, expiry_factor=0.05, staleness_factor=0.05))
        assert alerts == []


# ---------------------------------------------------------------------------
# CredentialAlertEngine - alerts_by_severity
# ---------------------------------------------------------------------------

class TestAlertsBySeverity:
    def test_returns_all_severity_keys(self):
        engine = CredentialAlertEngine()
        grouped = engine.alerts_by_severity([_score(score=0.85)])
        for sev in AlertSeverity:
            assert sev in grouped

    def test_critical_alerts_in_critical_bucket(self):
        engine = CredentialAlertEngine()
        grouped = engine.alerts_by_severity([_score(score=0.90)])
        assert len(grouped[AlertSeverity.CRITICAL]) > 0

    def test_no_alerts_all_buckets_empty(self):
        engine = CredentialAlertEngine()
        grouped = engine.alerts_by_severity([_score(score=0.05, staleness_factor=0.05, expiry_factor=0.05)])
        assert all(len(v) == 0 for v in grouped.values())


# ---------------------------------------------------------------------------
# Custom rules
# ---------------------------------------------------------------------------

class TestCustomRules:
    def test_custom_rule_replaces_defaults(self):
        custom_rule = AlertRule(
            name="MY_RULE",
            severity=AlertSeverity.LOW,
            predicate=lambda r: r.score > 0.0,
            message_template="custom alert for {edge_id}",
        )
        engine = CredentialAlertEngine(rules=[custom_rule])
        alerts = engine.evaluate([_score(score=0.50)])
        assert all(a.rule_name == "MY_RULE" for a in alerts)

    def test_empty_rules_no_alerts(self):
        engine = CredentialAlertEngine(rules=[])
        alerts = engine.evaluate([_score(score=0.99)])
        assert alerts == []
