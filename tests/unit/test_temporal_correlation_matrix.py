"""
tests/unit/test_temporal_correlation_matrix.py - Tests for TemporalCorrelationMatrix.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from arf_rt.temporal.correlation_matrix import (
    PairwiseTemporalOverlap,
    TemporalCorrelationMatrix,
)
from arf_rt.temporal.hints import TemporalHint


UTC = timezone.utc


class TestTemporalCorrelationMatrix:
    def test_complete_overlap(self) -> None:
        t0 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        t1 = t0 + timedelta(hours=2)
        h1 = TemporalHint(edge_id="e1", credential_issued=t0, credential_expiry=t1)
        h2 = TemporalHint(edge_id="e2", credential_issued=t0, credential_expiry=t1)

        matrix = TemporalCorrelationMatrix()
        res = matrix.compare_pair(h1, h2)

        assert res.overlap_seconds == 7200.0
        assert res.jaccard_similarity == pytest.approx(1.0)
        assert res.is_concurrent is True

    def test_disjoint_windows(self) -> None:
        t0 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        t1 = t0 + timedelta(hours=1)
        t2 = t0 + timedelta(hours=2)
        t3 = t0 + timedelta(hours=3)

        h1 = TemporalHint(edge_id="e1", credential_issued=t0, credential_expiry=t1)
        h2 = TemporalHint(edge_id="e2", credential_issued=t2, credential_expiry=t3)

        matrix = TemporalCorrelationMatrix()
        res = matrix.compare_pair(h1, h2)

        assert res.overlap_seconds == 0.0
        assert res.jaccard_similarity == 0.0
        assert res.is_concurrent is False

    def test_partial_overlap(self) -> None:
        t0 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        # h1: 10:00 - 11:00 (1 hour = 3600s)
        h1 = TemporalHint(edge_id="e1", credential_issued=t0, credential_expiry=t0 + timedelta(hours=1))
        # h2: 10:30 - 11:30 (1 hour)
        h2 = TemporalHint(edge_id="e2", credential_issued=t0 + timedelta(minutes=30), credential_expiry=t0 + timedelta(minutes=90))

        matrix = TemporalCorrelationMatrix()
        res = matrix.compare_pair(h1, h2)

        # Overlap: 10:30 - 11:00 (30 mins = 1800s)
        # Union: 10:00 - 11:30 (90 mins = 5400s)
        # Jaccard = 1800 / 5400 = 1/3
        assert res.overlap_seconds == 1800.0
        assert res.union_seconds == 5400.0
        assert pytest.approx(res.jaccard_similarity, 0.001) == (1.0 / 3.0)
        assert res.is_concurrent is True

    def test_compute_matrix_symmetric(self) -> None:
        t0 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        h1 = TemporalHint(edge_id="e1", credential_issued=t0, credential_expiry=t0 + timedelta(hours=1))
        h2 = TemporalHint(edge_id="e2", credential_issued=t0, credential_expiry=t0 + timedelta(hours=2))

        matrix = TemporalCorrelationMatrix()
        mat = matrix.compute_matrix([h1, h2])

        assert ("e1", "e2") in mat
        assert ("e2", "e1") in mat
        assert mat[("e1", "e2")].overlap_seconds == mat[("e2", "e1")].overlap_seconds

    def test_find_concurrent_pairs(self) -> None:
        t0 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        h1 = TemporalHint(edge_id="e1", credential_issued=t0, credential_expiry=t0 + timedelta(hours=1))
        h2 = TemporalHint(edge_id="e2", credential_issued=t0, credential_expiry=t0 + timedelta(hours=2))
        h3 = TemporalHint(edge_id="e3", credential_issued=t0 + timedelta(hours=5), credential_expiry=t0 + timedelta(hours=6))

        matrix = TemporalCorrelationMatrix()
        concurrent = matrix.find_concurrent_pairs([h1, h2, h3])

        assert len(concurrent) == 1
        assert (concurrent[0].edge_a, concurrent[0].edge_b) == ("e1", "e2")

    def test_find_synchronized_clusters(self) -> None:
        t0 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        # Group A: e1, e2, e3 share identical or near identical windows
        h1 = TemporalHint(edge_id="e1", credential_issued=t0, credential_expiry=t0 + timedelta(hours=1))
        h2 = TemporalHint(edge_id="e2", credential_issued=t0, credential_expiry=t0 + timedelta(hours=1))
        h3 = TemporalHint(edge_id="e3", credential_issued=t0, credential_expiry=t0 + timedelta(hours=1))
        # Group B: e4 separate
        h4 = TemporalHint(edge_id="e4", credential_issued=t0 + timedelta(hours=10), credential_expiry=t0 + timedelta(hours=12))

        matrix = TemporalCorrelationMatrix()
        clusters = matrix.find_synchronized_clusters([h1, h2, h3, h4], min_jaccard=0.90)

        assert len(clusters) == 1
        assert sorted(clusters[0]) == ["e1", "e2", "e3"]
