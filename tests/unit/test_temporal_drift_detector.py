"""
tests/unit/test_temporal_drift_detector.py - Unit tests for TemporalDriftDetector.

Validates new/removed credential detection, expiry and staleness drift events,
threshold enforcement, DriftReport summary, and by_kind grouping.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.temporal_drift_detector import (
    DriftKind,
    DriftReport,
    TemporalDriftDetector,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)


def _hint(
    edge_id: str = "e1",
    expiry_offset: float | None = 7200,   # seconds from NOW
    last_used_offset: float | None = -3600,  # seconds from NOW (negative = in past)
) -> TemporalHint:
    expiry = (NOW + timedelta(seconds=expiry_offset)) if expiry_offset is not None else None
    last_used = (NOW + timedelta(seconds=last_used_offset)) if last_used_offset is not None else None
    return TemporalHint(edge_id=edge_id, credential_expiry=expiry, last_used=last_used)


def _detector(**kwargs) -> TemporalDriftDetector:
    return TemporalDriftDetector(reference_time=NOW, **kwargs)


# ---------------------------------------------------------------------------
# DriftReport
# ---------------------------------------------------------------------------

class TestDriftReport:
    def test_has_drift_true_when_events(self):
        detector = _detector()
        baseline = [_hint("a")]
        current = [_hint("a"), _hint("b")]
        report = detector.compare(baseline, current)
        assert report.has_drift is True

    def test_has_drift_false_when_no_events(self):
        detector = _detector()
        h = _hint("a")
        report = detector.compare([h], [h])
        assert report.has_drift is False

    def test_counts_correct(self):
        detector = _detector()
        report = detector.compare([_hint("a"), _hint("b")], [_hint("c")])
        assert report.baseline_count == 2
        assert report.current_count == 1

    def test_by_kind_has_all_keys(self):
        detector = _detector()
        report = detector.compare([], [])
        for kind in DriftKind:
            assert kind in report.by_kind

    def test_summary_contains_counts(self):
        detector = _detector()
        report = detector.compare([_hint("a")], [_hint("b")])
        summary = report.summary()
        assert "Baseline edges" in summary
        assert "Current edges" in summary


# ---------------------------------------------------------------------------
# New credential detection
# ---------------------------------------------------------------------------

class TestNewCredential:
    def test_new_edge_detected(self):
        detector = _detector()
        report = detector.compare([_hint("a")], [_hint("a"), _hint("b")])
        new_events = report.by_kind[DriftKind.NEW_CREDENTIAL]
        assert len(new_events) == 1
        assert new_events[0].edge_id == "b"

    def test_no_new_credentials(self):
        detector = _detector()
        report = detector.compare([_hint("a")], [_hint("a")])
        assert report.by_kind[DriftKind.NEW_CREDENTIAL] == []

    def test_multiple_new_edges(self):
        detector = _detector()
        report = detector.compare([], [_hint("x"), _hint("y"), _hint("z")])
        assert len(report.by_kind[DriftKind.NEW_CREDENTIAL]) == 3


# ---------------------------------------------------------------------------
# Removed credential detection
# ---------------------------------------------------------------------------

class TestRemovedCredential:
    def test_removed_edge_detected(self):
        detector = _detector()
        report = detector.compare([_hint("a"), _hint("b")], [_hint("a")])
        removed = report.by_kind[DriftKind.REMOVED_CREDENTIAL]
        assert len(removed) == 1
        assert removed[0].edge_id == "b"

    def test_no_removed_credentials(self):
        detector = _detector()
        report = detector.compare([_hint("a")], [_hint("a")])
        assert report.by_kind[DriftKind.REMOVED_CREDENTIAL] == []


# ---------------------------------------------------------------------------
# Expiry drift detection
# ---------------------------------------------------------------------------

class TestExpiryDrift:
    def test_expiry_advanced_when_shorter(self):
        """Expiry moved earlier → EXPIRY_ADVANCED."""
        detector = _detector(expiry_threshold_seconds=60)
        base = _hint("e", expiry_offset=7200)
        curr = _hint("e", expiry_offset=3600)   # 3600 s earlier
        report = detector.compare([base], [curr])
        events = report.by_kind[DriftKind.EXPIRY_ADVANCED]
        assert len(events) == 1
        assert events[0].delta_seconds == pytest.approx(-3600.0)

    def test_expiry_extended_when_longer(self):
        """Expiry moved later → EXPIRY_EXTENDED."""
        detector = _detector(expiry_threshold_seconds=60)
        base = _hint("e", expiry_offset=3600)
        curr = _hint("e", expiry_offset=7200)   # 3600 s later
        report = detector.compare([base], [curr])
        events = report.by_kind[DriftKind.EXPIRY_EXTENDED]
        assert len(events) == 1
        assert events[0].delta_seconds == pytest.approx(3600.0)

    def test_small_expiry_change_ignored(self):
        """Change below threshold is not reported."""
        detector = _detector(expiry_threshold_seconds=3600)
        base = _hint("e", expiry_offset=7200)
        curr = _hint("e", expiry_offset=7300)   # only 100 s diff
        report = detector.compare([base], [curr])
        assert report.by_kind[DriftKind.EXPIRY_EXTENDED] == []
        assert report.by_kind[DriftKind.EXPIRY_ADVANCED] == []

    def test_no_expiry_metadata_skipped(self):
        detector = _detector()
        base = _hint("e", expiry_offset=None)
        curr = _hint("e", expiry_offset=None)
        report = detector.compare([base], [curr])
        assert not report.has_drift


# ---------------------------------------------------------------------------
# Staleness drift detection
# ---------------------------------------------------------------------------

class TestStalenessDrift:
    def test_staleness_increased_when_older(self):
        """last_used moved further in the past → STALENESS_INCREASED."""
        detector = _detector(staleness_threshold_seconds=60)
        base = _hint("e", last_used_offset=-3600)
        curr = _hint("e", last_used_offset=-10800)  # 7200 s older
        report = detector.compare([base], [curr])
        events = report.by_kind[DriftKind.STALENESS_INCREASED]
        assert len(events) == 1
        assert events[0].delta_seconds == pytest.approx(-7200.0)

    def test_staleness_decreased_when_fresher(self):
        """last_used moved closer to now → STALENESS_DECREASED."""
        detector = _detector(staleness_threshold_seconds=60)
        base = _hint("e", last_used_offset=-10800)
        curr = _hint("e", last_used_offset=-3600)   # 7200 s fresher
        report = detector.compare([base], [curr])
        events = report.by_kind[DriftKind.STALENESS_DECREASED]
        assert len(events) == 1

    def test_small_staleness_change_ignored(self):
        detector = _detector(staleness_threshold_seconds=7200)
        base = _hint("e", last_used_offset=-3600)
        curr = _hint("e", last_used_offset=-3700)   # 100 s diff
        report = detector.compare([base], [curr])
        assert report.by_kind[DriftKind.STALENESS_INCREASED] == []

    def test_no_last_used_metadata_skipped(self):
        detector = _detector()
        base = _hint("e", last_used_offset=None)
        curr = _hint("e", last_used_offset=None)
        report = detector.compare([base], [curr])
        assert not report.has_drift
