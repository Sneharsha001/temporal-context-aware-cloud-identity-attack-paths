"""
tests/unit/test_anomaly_classifier.py - Unit tests for AnomalyClassifier.
"""

from __future__ import annotations

import pytest

from arf_rt.temporal.anomaly_classifier import AnomalyClassifier, SeverityTier
from arf_rt.temporal.verdict import TemporalVerdict, VerdictKind


class TestAnomalyClassifier:
    def test_classify_tc1_causal_inversion(self) -> None:
        anomaly = AnomalyClassifier.classify_constraint_violation("TC-1")
        assert anomaly.severity == SeverityTier.HIGH
        assert anomaly.title == "Causal Order Inversion"
        assert "clock drift" in anomaly.remediation

    def test_classify_tc2_expiry(self) -> None:
        anomaly = AnomalyClassifier.classify_constraint_violation("TC-2")
        assert anomaly.severity == SeverityTier.CRITICAL
        assert anomaly.title == "Expired Credential Usage"
        assert "Revoke active sessions" in anomaly.remediation

    def test_classify_tc4_stale(self) -> None:
        anomaly = AnomalyClassifier.classify_constraint_violation("TC-4")
        assert anomaly.severity == SeverityTier.MEDIUM
        assert "Dormant Credential" in anomaly.title

    def test_classify_window_burst(self) -> None:
        anomaly = AnomalyClassifier.classify_window_finding("Rapid burst of 15 AssumeRole API calls")
        assert anomaly.severity == SeverityTier.HIGH
        assert anomaly.anomaly_id == "WIN-BURST"

    def test_classify_window_concurrency(self) -> None:
        anomaly = AnomalyClassifier.classify_window_finding("Impossible session concurrency across us-east-1 and ap-southeast-1")
        assert anomaly.severity == SeverityTier.CRITICAL
        assert anomaly.anomaly_id == "WIN-CONCURRENCY"

    def test_classify_path_sorting(self) -> None:
        verdict = TemporalVerdict(
            kind=VerdictKind.INFEASIBLE,
            violated_constraint="TC-4",  # MEDIUM
            reason="Key not used for 180 days.",
        )
        findings = [
            "Impossible session concurrency detected",  # CRITICAL
            "Rapid burst of AssumeRole calls",          # HIGH
        ]
        anomalies = AnomalyClassifier.classify_path(verdict, findings)

        assert len(anomalies) == 3
        # Ensure sorted descending: CRITICAL, HIGH, MEDIUM
        assert anomalies[0].severity == SeverityTier.CRITICAL
        assert anomalies[1].severity == SeverityTier.HIGH
        assert anomalies[2].severity == SeverityTier.MEDIUM
