"""
arf_rt/temporal/timeline.py - Credential lifecycle and timeline reconstruction.

Reconstructs chronological timelines for multi-hop attack paths, generates ASCII
lifecycle visualizations, and calculates credential validity overlaps across hops.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from arf_rt.temporal.hints import TemporalHint


@dataclass(frozen=True)
class TimelineEvent:
    """A discrete temporal milestone in the path execution lifecycle."""
    timestamp: datetime
    edge_id: str
    event_type: str  # 'ISSUED', 'OBSERVED_START', 'OBSERVED_END', 'EXPIRED'
    description: str


class CredentialTimelineBuilder:
    """
    Builds chronological timelines and ASCII Gantt-style charts
    for credential lifecycle analysis along candidate attack paths.
    """

    def __init__(self, edge_ids: list[str], hints: dict[str, TemporalHint]) -> None:
        self.edge_ids = edge_ids
        self.hints = hints

    def extract_events(self) -> list[TimelineEvent]:
        """Extract all timestamped milestones along the path, sorted chronologically."""
        events: list[TimelineEvent] = []

        for eid in self.edge_ids:
            hint = self.hints.get(eid)
            if not hint:
                continue

            if hint.credential_issued:
                events.append(TimelineEvent(
                    timestamp=hint.credential_issued,
                    edge_id=eid,
                    event_type="ISSUED",
                    description=f"Credential issued for {eid}",
                ))
            if hint.earliest_observed:
                events.append(TimelineEvent(
                    timestamp=hint.earliest_observed,
                    edge_id=eid,
                    event_type="OBSERVED_START",
                    description=f"First activity observed on {eid}",
                ))
            if hint.latest_observed and hint.latest_observed != hint.earliest_observed:
                events.append(TimelineEvent(
                    timestamp=hint.latest_observed,
                    edge_id=eid,
                    event_type="OBSERVED_END",
                    description=f"Last activity observed on {eid}",
                ))
            if hint.credential_expiry:
                events.append(TimelineEvent(
                    timestamp=hint.credential_expiry,
                    edge_id=eid,
                    event_type="EXPIRED",
                    description=f"Credential expiry for {eid}",
                ))

        events.sort(key=lambda ev: ev.timestamp)
        return events

    def generate_ascii_gantt(self, width: int = 50) -> str:
        """
        Generate an ASCII Gantt chart illustrating the validity intervals of credentials.
        """
        valid_intervals: list[tuple[str, datetime, datetime]] = []
        for eid in self.edge_ids:
            hint = self.hints.get(eid)
            if hint and hint.credential_issued and hint.credential_expiry:
                valid_intervals.append((eid, hint.credential_issued, hint.credential_expiry))

        if not valid_intervals:
            return "Insufficient timestamp intervals to generate ASCII chart."

        min_time = min(start for _, start, _ in valid_intervals)
        max_time = max(end for _, _, end in valid_intervals)
        total_span = (max_time - min_time).total_seconds()

        if total_span <= 0:
            return "Instantaneous timeline: total duration 0 seconds."

        lines = [
            f"Timeline Span: {min_time.isoformat()} -> {max_time.isoformat()} ({int(total_span)}s)",
            "-" * (width + 25),
        ]

        for eid, start, end in valid_intervals:
            start_offset = (start - min_time).total_seconds()
            duration = (end - start).total_seconds()

            start_col = int((start_offset / total_span) * width)
            bar_len = max(1, int((duration / total_span) * width))

            bar = " " * start_col + "[" + "=" * max(0, bar_len - 2) + "]"
            bar = bar.ljust(width)
            lines.append(f"{eid[:20]:<20} |{bar}|")

        lines.append("-" * (width + 25))
        return "\n".join(lines)

    def to_markdown_table(self) -> str:
        """Format the chronological event log as a GitHub-flavored Markdown table."""
        events = self.extract_events()
        if not events:
            return "No temporal milestones available for this path."

        lines = [
            "| Timestamp (UTC) | Hop / Edge | Event Type | Description |",
            "|---|---|---|---|",
        ]
        for ev in events:
            ts_str = ev.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"| {ts_str} | `{ev.edge_id}` | `{ev.event_type}` | {ev.description} |")

        return "\n".join(lines)
