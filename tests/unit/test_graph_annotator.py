"""
tests/unit/test_graph_annotator.py - Unit tests for TemporalGraphAnnotator.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arf_rt.temporal.graph_annotator import TemporalGraphAnnotator
from arf_rt.temporal.hints import TemporalHint


@pytest.fixture
def annotator_fixtures() -> tuple[dict[str, TemporalHint], datetime]:
    utc = timezone.utc
    ref = datetime(2026, 10, 24, 12, 0, 0, tzinfo=utc)

    # Active edge
    active_issued = ref - timedelta(hours=1)
    active_expiry = ref + timedelta(hours=1)
    h_active = TemporalHint(
        edge_id="user→admin",
        credential_issued=active_issued,
        credential_expiry=active_expiry,
        last_used=active_issued,
    )

    # Expired edge
    exp_issued = ref - timedelta(hours=5)
    exp_expiry = ref - timedelta(hours=1)
    h_expired = TemporalHint(
        edge_id="user→dev",
        credential_issued=exp_issued,
        credential_expiry=exp_expiry,
        last_used=exp_issued,
    )

    # Stale edge (last used 120 days ago)
    stale_used = ref - timedelta(days=120)
    h_stale = TemporalHint(
        edge_id="dev→prod",
        last_used=stale_used,
    )

    hints = {
        "user→admin": h_active,
        "user→dev": h_expired,
        "dev→prod": h_stale,
    }
    return hints, ref


class TestTemporalGraphAnnotator:
    def test_annotate_active_edge(
        self, annotator_fixtures: tuple[dict[str, TemporalHint], datetime]
    ) -> None:
        hints, ref = annotator_fixtures
        annotator = TemporalGraphAnnotator(hints=hints, reference_time=ref)
        edge = annotator.annotate_edge("user", "admin")

        assert edge.is_expired is False
        assert edge.is_stale is False
        assert edge.dot_color == "darkgreen"
        assert edge.validity_duration_seconds == 7200.0

    def test_annotate_expired_edge(
        self, annotator_fixtures: tuple[dict[str, TemporalHint], datetime]
    ) -> None:
        hints, ref = annotator_fixtures
        annotator = TemporalGraphAnnotator(hints=hints, reference_time=ref)
        edge = annotator.annotate_edge("user", "dev")

        assert edge.is_expired is True
        assert edge.dot_color == "red"
        assert edge.dot_style == "dashed"

    def test_annotate_stale_edge(
        self, annotator_fixtures: tuple[dict[str, TemporalHint], datetime]
    ) -> None:
        hints, ref = annotator_fixtures
        annotator = TemporalGraphAnnotator(hints=hints, reference_time=ref)
        edge = annotator.annotate_edge("dev", "prod")

        assert edge.is_stale is True
        assert edge.dot_color == "orange"
        assert edge.dot_style == "dotted"

    def test_annotate_graph_edges_batch(
        self, annotator_fixtures: tuple[dict[str, TemporalHint], datetime]
    ) -> None:
        hints, ref = annotator_fixtures
        annotator = TemporalGraphAnnotator(hints=hints, reference_time=ref)
        edges = [("user", "admin"), ("user", "dev"), ("dev", "prod"), ("unknown", "target")]
        annotated = annotator.annotate_graph_edges(edges)

        assert len(annotated) == 4
        assert annotated[3].dot_color == "gray"
