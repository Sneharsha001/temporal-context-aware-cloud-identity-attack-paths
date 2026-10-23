"""
tests/unit/test_temporal_timeline.py - Unit tests for CredentialTimelineBuilder.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.timeline import CredentialTimelineBuilder


@pytest.fixture
def timeline_hints() -> dict[str, TemporalHint]:
    utc = timezone.utc
    return {
        "edge_hop1": TemporalHint(
            edge_id="edge_hop1",
            credential_issued=datetime(2026, 10, 23, 10, 0, 0, tzinfo=utc),
            earliest_observed=datetime(2026, 10, 23, 10, 5, 0, tzinfo=utc),
            latest_observed=datetime(2026, 10, 23, 10, 20, 0, tzinfo=utc),
            credential_expiry=datetime(2026, 10, 23, 11, 0, 0, tzinfo=utc),
        ),
        "edge_hop2": TemporalHint(
            edge_id="edge_hop2",
            credential_issued=datetime(2026, 10, 23, 10, 25, 0, tzinfo=utc),
            earliest_observed=datetime(2026, 10, 23, 10, 30, 0, tzinfo=utc),
            latest_observed=datetime(2026, 10, 23, 10, 45, 0, tzinfo=utc),
            credential_expiry=datetime(2026, 10, 23, 11, 25, 0, tzinfo=utc),
        ),
    }


class TestCredentialTimelineBuilder:
    def test_extract_events_chronological_order(
        self, timeline_hints: dict[str, TemporalHint]
    ) -> None:
        builder = CredentialTimelineBuilder(["edge_hop1", "edge_hop2"], timeline_hints)
        events = builder.extract_events()

        assert len(events) == 8
        for i in range(len(events) - 1):
            assert events[i].timestamp <= events[i + 1].timestamp

        first_event = events[0]
        assert first_event.edge_id == "edge_hop1"
        assert first_event.event_type == "ISSUED"

    def test_generate_ascii_gantt(
        self, timeline_hints: dict[str, TemporalHint]
    ) -> None:
        builder = CredentialTimelineBuilder(["edge_hop1", "edge_hop2"], timeline_hints)
        gantt = builder.generate_ascii_gantt(width=40)

        assert "Timeline Span:" in gantt
        assert "edge_hop1" in gantt
        assert "edge_hop2" in gantt
        assert "[" in gantt
        assert "]" in gantt

    def test_ascii_gantt_insufficient_timestamps(self) -> None:
        hints = {"sparse_edge": TemporalHint(edge_id="sparse_edge")}
        builder = CredentialTimelineBuilder(["sparse_edge"], hints)
        gantt = builder.generate_ascii_gantt()
        assert "Insufficient timestamp intervals" in gantt

    def test_to_markdown_table(
        self, timeline_hints: dict[str, TemporalHint]
    ) -> None:
        builder = CredentialTimelineBuilder(["edge_hop1", "edge_hop2"], timeline_hints)
        table = builder.to_markdown_table()

        assert "| Timestamp (UTC) | Hop / Edge | Event Type | Description |" in table
        assert "`edge_hop1`" in table
        assert "`edge_hop2`" in table
        assert "`ISSUED`" in table
        assert "`EXPIRED`" in table
