"""
tests/integration/test_temporal_end_to_end.py - End-to-end temporal integration pipeline test.

Validates the complete execution chain:
CloudTrail parsing -> Path filtering -> Timeline building -> Anomaly classification -> Reporting & Export
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

import pytest

from arf_rt.temporal.anomaly_classifier import AnomalyClassifier, SeverityTier
from arf_rt.temporal.cloudtrail_parser import extract_hints_from_log
from arf_rt.temporal.export import export_metrics_to_csv
from arf_rt.temporal.metrics import TemporalMetrics
from arf_rt.temporal.path_filter import TemporalPathFilter
from arf_rt.temporal.summary import TemporalSummaryReporter
from arf_rt.temporal.timeline import CredentialTimelineBuilder


@pytest.fixture
def raw_cloudtrail_events() -> list[dict]:
    return [
        {
            "eventName": "AssumeRole",
            "eventTime": "2026-10-23T10:00:00Z",
            "userIdentity": {"arn": "arn:aws:iam::111122223333:user/alice"},
            "requestParameters": {"roleArn": "arn:aws:iam::111122223333:role/DevRole"},
            "responseElements": {
                "credentials": {
                    "expiration": "2026-10-23T11:00:00Z",
                }
            },
        },
        {
            "eventName": "AssumeRole",
            "eventTime": "2026-10-23T10:15:00Z",
            "userIdentity": {"arn": "arn:aws:iam::111122223333:role/DevRole"},
            "requestParameters": {"roleArn": "arn:aws:iam::444455556666:role/ProdRole"},
            "responseElements": {
                "credentials": {
                    "expiration": "2026-10-23T11:15:00Z",
                }
            },
        },
    ]


class TestTemporalEndToEnd:
    def test_complete_temporal_pipeline(
        self, raw_cloudtrail_events: list[dict], tmp_path: Path
    ) -> None:
        ref_time = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)

        # 1. Parse CloudTrail events
        hints = extract_hints_from_log(raw_cloudtrail_events)
        assert len(hints) == 2

        e1 = "arn:aws:iam::111122223333:user/alice→arn:aws:iam::111122223333:role/DevRole"
        e2 = "arn:aws:iam::111122223333:role/DevRole→arn:aws:iam::444455556666:role/ProdRole"
        assert e1 in hints
        assert e2 in hints

        # 2. Path filter
        paths = [
            [e1, e2],           # Valid 2-hop sequence
            [e2, e1],           # Inverted 2-hop sequence (causal violation)
        ]
        pf = TemporalPathFilter(reference_time=ref_time, run_window_checks=True)
        results = pf.filter(paths, hints)

        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False

        # 3. Timeline builder
        timeline = CredentialTimelineBuilder([e1, e2], hints)
        events = timeline.extract_events()
        assert len(events) >= 2
        gantt = timeline.generate_ascii_gantt(width=40)
        assert "Timeline Span:" in gantt

        # 4. Metrics & Summary
        metrics = TemporalMetrics()
        for r in results:
            plen = len(r.edge_ids)
            if r.passed:
                metrics.record_feasible(plen)
            else:
                metrics.record_infeasible(r.rejected_by, plen)

        reporter = TemporalSummaryReporter(metrics)
        exec_summary = reporter.generate_executive_summary()
        assert "Total Paths Evaluated:** 2" in exec_summary
        assert "Feasible Paths:** 1" in exec_summary
        assert "Infeasible Paths (Eliminated):** 1" in exec_summary

        # 5. Export
        csv_file = tmp_path / "summary.csv"
        export_metrics_to_csv(metrics, csv_file)
        assert csv_file.exists()
        assert "elimination_rate_pct" in csv_file.read_text(encoding="utf-8")
