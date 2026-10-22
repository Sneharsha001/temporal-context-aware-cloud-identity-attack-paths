"""
tests/unit/test_scenario_enricher.py - Unit tests for arf_rt.temporal.scenario_enricher.
"""

from __future__ import annotations
from typing import Any

import pytest

from arf_rt.temporal.scenario_enricher import enrich_edges_with_hints, hint_coverage_report
from arf_rt.temporal.hints import TemporalHint


def _make_ct_event(source: str, target: str, time: str = "2025-06-15T10:00:00Z") -> dict:
    return {
        "eventName": "AssumeRole",
        "eventTime": time,
        "userIdentity": {"arn": source},
        "requestParameters": {"roleArn": target},
        "responseElements": {"credentials": {"expiration": "2025-06-15T11:00:00Z"}},
    }


SRC = "arn:aws:iam::111111111111:user/alice"
TGT = "arn:aws:iam::222222222222:role/DevRole"
EDGE_ID = f"{SRC}→{TGT}"


class TestEnrichEdgesWithHints:
    def test_direct_match_returns_hint(self) -> None:
        events = [_make_ct_event(SRC, TGT)]
        hints = enrich_edges_with_hints([EDGE_ID], events)
        assert EDGE_ID in hints
        assert hints[EDGE_ID].earliest_observed is not None

    def test_no_match_returns_empty_hint(self) -> None:
        hints = enrich_edges_with_hints(["unknown-edge"], [])
        assert hints["unknown-edge"].earliest_observed is None

    def test_fallback_hint_used_when_no_match(self) -> None:
        from datetime import datetime, timezone
        fallback = TemporalHint(edge_id="fallback", last_used=datetime(2025, 1, 1, tzinfo=timezone.utc))
        hints = enrich_edges_with_hints(["missing"], [], fallback_hint=fallback)
        assert hints["missing"].last_used is not None

    def test_multiple_edges_enriched(self) -> None:
        src2 = "arn:aws:iam::222222222222:role/DevRole"
        tgt2 = "arn:aws:iam::333333333333:role/Admin"
        events = [_make_ct_event(SRC, TGT), _make_ct_event(src2, tgt2)]
        ids = [EDGE_ID, f"{src2}→{tgt2}"]
        hints = enrich_edges_with_hints(ids, events)
        assert len(hints) == 2
        for eid in ids:
            assert hints[eid].earliest_observed is not None

    def test_empty_edges_returns_empty_dict(self) -> None:
        assert enrich_edges_with_hints([], []) == {}


class TestHintCoverageReport:
    def test_full_coverage(self) -> None:
        from datetime import datetime, timezone
        t = datetime(2025, 6, 15, 10, tzinfo=timezone.utc)
        hints = {
            "e1": TemporalHint(edge_id="e1", earliest_observed=t, latest_observed=t),
            "e2": TemporalHint(edge_id="e2", earliest_observed=t, latest_observed=t),
        }
        report = hint_coverage_report(["e1", "e2"], hints)
        assert report["total"] == 2
        assert report["with_observation"] == 2
        assert report["coverage_pct"] == 100.0

    def test_zero_coverage(self) -> None:
        hints = {"e1": TemporalHint(edge_id="e1")}
        report = hint_coverage_report(["e1"], hints)
        assert report["coverage_pct"] == 0.0

    def test_empty_edges(self) -> None:
        report = hint_coverage_report([], {})
        assert report["total"] == 0
        assert report["coverage_pct"] == 0.0
