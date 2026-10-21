"""
tests/unit/test_window_analyzer.py - Unit tests for arf_rt.temporal.window_analyzer.

Covers impossible concurrency detection, burst detection, and cross-account
credential reuse detection with clean and anomalous scenarios.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.window_analyzer import (
    WindowAnalysisResult,
    detect_burst,
    detect_impossible_concurrency,
    detect_cross_account_reuse,
)


UTC = timezone.utc


def _dt(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2025, 6, 15, hour, minute, second, tzinfo=UTC)


def make_hint(
    edge_id: str,
    earliest: datetime | None = None,
    latest: datetime | None = None,
    issued: datetime | None = None,
) -> TemporalHint:
    return TemporalHint(
        edge_id=edge_id,
        earliest_observed=earliest,
        latest_observed=latest,
        credential_issued=issued,
    )


# ---------------------------------------------------------------------------
# detect_impossible_concurrency
# ---------------------------------------------------------------------------


class TestDetectImpossibleConcurrency:
    def test_clean_when_hops_are_spaced(self) -> None:
        path = [
            make_hint("e1", earliest=_dt(8), latest=_dt(8, 0, 0)),
            make_hint("e2", earliest=_dt(8, 0, 5)),
        ]
        result = detect_impossible_concurrency(path, min_human_latency_seconds=2.0)
        assert not result.suspicious

    def test_anomaly_when_hops_sub_second(self) -> None:
        t = _dt(8, 0, 0)
        path = [
            make_hint("e1", earliest=t, latest=t),
            make_hint("e2", earliest=t),  # 0s gap
        ]
        result = detect_impossible_concurrency(path, min_human_latency_seconds=2.0)
        assert result.suspicious
        assert "e1" in result.affected_edge_ids
        assert "e2" in result.affected_edge_ids

    def test_clean_when_data_missing(self) -> None:
        path = [make_hint("e1"), make_hint("e2")]
        result = detect_impossible_concurrency(path)
        assert not result.suspicious

    def test_single_hop_always_clean(self) -> None:
        path = [make_hint("e1", earliest=_dt(8), latest=_dt(8))]
        result = detect_impossible_concurrency(path)
        assert not result.suspicious


# ---------------------------------------------------------------------------
# detect_burst
# ---------------------------------------------------------------------------


class TestDetectBurst:
    def test_clean_when_below_threshold(self) -> None:
        path = [
            make_hint(f"e{i}", earliest=_dt(8) + timedelta(minutes=i * 5))
            for i in range(3)
        ]
        result = detect_burst(path, window_seconds=60.0, max_hops_in_window=5)
        assert not result.suspicious

    def test_anomaly_when_too_many_hops_in_window(self) -> None:
        # 6 hops all within 10 seconds — exceeds max_hops_in_window=5
        t0 = _dt(8)
        path = [
            make_hint(f"e{i}", earliest=t0 + timedelta(seconds=i))
            for i in range(6)
        ]
        result = detect_burst(path, window_seconds=60.0, max_hops_in_window=5)
        assert result.suspicious

    def test_empty_path_is_clean(self) -> None:
        assert not detect_burst([], window_seconds=60.0, max_hops_in_window=3).suspicious


# ---------------------------------------------------------------------------
# detect_cross_account_reuse
# ---------------------------------------------------------------------------


class TestDetectCrossAccountReuse:
    def test_clean_when_single_account(self) -> None:
        issued = _dt(8)
        path = [
            make_hint("arn:aws:iam::111111111111:role/A→arn:aws:iam::111111111111:role/B", issued=issued),
        ]
        result = detect_cross_account_reuse(path)
        assert not result.suspicious

    def test_anomaly_when_same_credential_across_accounts(self) -> None:
        issued = _dt(8)
        path = [
            make_hint("arn:aws:iam::111111111111:user/alice→arn:aws:iam::222222222222:role/Dev", issued=issued),
            make_hint("arn:aws:iam::333333333333:role/Ops→arn:aws:iam::444444444444:role/Admin", issued=issued),
        ]
        result = detect_cross_account_reuse(path)
        assert result.suspicious

    def test_clean_when_no_credential_issued(self) -> None:
        path = [make_hint("e1"), make_hint("e2")]
        result = detect_cross_account_reuse(path)
        assert not result.suspicious
