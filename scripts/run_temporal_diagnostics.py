#!/usr/bin/env python3
"""
scripts/run_temporal_diagnostics.py - Operational diagnostic and health verification CLI.

Runs self-contained integration checks across all temporal sub-package components
to verify runtime operational readiness.

Usage::

    python scripts/run_temporal_diagnostics.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arf_rt.temporal.anomaly_classifier import AnomalyClassifier, SeverityTier
from arf_rt.temporal.audit_log import TemporalAuditLog
from arf_rt.temporal.batch_runner import PathFeasibilityBatchRunner
from arf_rt.temporal.config import TemporalConfig
from arf_rt.temporal.evaluator import TemporalEvaluator
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.metrics import TemporalMetrics
from arf_rt.temporal.path_filter import TemporalPathFilter
from arf_rt.temporal.summary import TemporalSummaryReporter
from arf_rt.temporal.timeline import CredentialTimelineBuilder
from arf_rt.temporal.verdict import TemporalVerdict, VerdictKind


def run_diagnostics() -> int:
    print("=" * 60)
    print("ARF-RT Temporal Subsystem Operational Diagnostics")
    print("=" * 60)

    utc = timezone.utc
    ref_time = datetime(2026, 10, 23, 12, 0, 0, tzinfo=utc)

    # 1. Component Instantiation
    print("[1/5] Checking component instantiation...", end=" ")
    cfg = TemporalConfig.permissive()
    ev = TemporalEvaluator(config=cfg, reference_time=ref_time)
    pf = TemporalPathFilter(config=cfg, reference_time=ref_time)
    metrics = TemporalMetrics()
    audit_log = TemporalAuditLog()
    batch_runner = PathFeasibilityBatchRunner(config=cfg, reference_time=ref_time)
    print("OK")

    # 2. Path Filter Execution
    print("[2/5] Checking path filter verification...", end=" ")
    hints = {
        "e1": TemporalHint(edge_id="e1", earliest_observed=datetime(2026, 10, 23, 10, 0, tzinfo=utc), last_used=datetime(2026, 10, 23, 10, 0, tzinfo=utc)),
        "e2": TemporalHint(edge_id="e2", earliest_observed=datetime(2026, 10, 23, 10, 15, tzinfo=utc), last_used=datetime(2026, 10, 23, 10, 15, tzinfo=utc)),
    }
    filter_results = pf.filter([["e1", "e2"]], hints)
    assert len(filter_results) == 1
    assert filter_results[0].passed is True
    print("OK")

    # 3. Anomaly Classifier
    print("[3/5] Checking anomaly classification rules...", end=" ")
    anomaly = AnomalyClassifier.classify_constraint_violation("TC-2", "Token expired")
    assert anomaly.severity == SeverityTier.CRITICAL
    print("OK")

    # 4. Timeline Builder
    print("[4/5] Checking credential timeline generator...", end=" ")
    timeline = CredentialTimelineBuilder(["e1", "e2"], hints)
    events = timeline.extract_events()
    assert len(events) >= 2
    print("OK")

    # 5. Summary Reporter
    print("[5/5] Checking summary report generator...", end=" ")
    metrics.record_feasible(path_length=2)
    reporter = TemporalSummaryReporter(metrics, audit_log)
    summary = reporter.generate_executive_summary()
    assert "Executive Summary" in summary
    print("OK")

    print("-" * 60)
    print("All temporal subsystem diagnostics PASSED (5/5). System ready.")
    print("-" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run_diagnostics())
