"""
arf_rt/temporal/temporal_drift_detector.py - Credential window drift detection.

Compares two snapshots of TemporalHint collections (baseline vs. current) and
identifies drift events: new credentials appearing, credentials disappearing,
expiry window shrinkage, and staleness increases beyond configurable thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Sequence

from arf_rt.temporal.hints import TemporalHint


class DriftKind(str, Enum):
    NEW_CREDENTIAL = "NEW_CREDENTIAL"          # edge appears in current but not baseline
    REMOVED_CREDENTIAL = "REMOVED_CREDENTIAL"  # edge in baseline but not current
    EXPIRY_ADVANCED = "EXPIRY_ADVANCED"        # expiry moved earlier (window shrank)
    EXPIRY_EXTENDED = "EXPIRY_EXTENDED"        # expiry pushed later (window grew)
    STALENESS_INCREASED = "STALENESS_INCREASED"  # last_used older in current vs. baseline
    STALENESS_DECREASED = "STALENESS_DECREASED"  # last_used fresher in current vs. baseline


@dataclass
class DriftEvent:
    """A detected change between baseline and current hint snapshots."""

    edge_id: str
    kind: DriftKind
    baseline_value: str | None   # human-readable representation of baseline field
    current_value: str | None    # human-readable representation of current field
    delta_seconds: float | None  # signed delta (positive = later/larger)
    detected_at: datetime

    def __str__(self) -> str:
        return (
            f"[{self.kind.value}] {self.edge_id}: "
            f"baseline={self.baseline_value!r} → current={self.current_value!r}"
            + (f" (Δ={self.delta_seconds:+.0f}s)" if self.delta_seconds is not None else "")
        )


@dataclass
class DriftReport:
    """Aggregated drift analysis between two hint snapshots."""

    events: list[DriftEvent]
    detected_at: datetime
    baseline_count: int
    current_count: int

    @property
    def has_drift(self) -> bool:
        return len(self.events) > 0

    @property
    def by_kind(self) -> dict[DriftKind, list[DriftEvent]]:
        result: dict[DriftKind, list[DriftEvent]] = {k: [] for k in DriftKind}
        for evt in self.events:
            result[evt.kind].append(evt)
        return result

    def summary(self) -> str:
        lines = [
            f"Drift Report — {self.detected_at.isoformat()}",
            f"  Baseline edges : {self.baseline_count}",
            f"  Current edges  : {self.current_count}",
            f"  Total events   : {len(self.events)}",
        ]
        by_kind = self.by_kind
        for kind, evts in by_kind.items():
            if evts:
                lines.append(f"  {kind.value}: {len(evts)}")
        return "\n".join(lines)


class TemporalDriftDetector:
    """
    Detects drift between two temporal hint snapshots.

    Parameters
    ----------
    expiry_threshold_seconds:
        Minimum absolute change in ``credential_expiry`` (in seconds) to
        qualify as a drift event. Defaults to 300 s (5 min).
    staleness_threshold_seconds:
        Minimum absolute change in ``last_used`` age (in seconds) to qualify
        as a staleness drift event. Defaults to 3600 s (1 h).
    reference_time:
        Instant used as "now" for relative age calculations. Defaults to
        ``datetime.now(tz=timezone.utc)``.
    """

    def __init__(
        self,
        expiry_threshold_seconds: float = 300.0,
        staleness_threshold_seconds: float = 3600.0,
        reference_time: datetime | None = None,
    ) -> None:
        self.expiry_threshold = expiry_threshold_seconds
        self.staleness_threshold = staleness_threshold_seconds
        self.reference_time = reference_time or datetime.now(tz=timezone.utc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compare(
        self,
        baseline: Sequence[TemporalHint],
        current: Sequence[TemporalHint],
    ) -> DriftReport:
        """
        Compare *baseline* hints against *current* hints and return a :class:`DriftReport`.
        """
        baseline_map = {h.edge_id: h for h in baseline}
        current_map = {h.edge_id: h for h in current}

        events: list[DriftEvent] = []
        now = self.reference_time

        # New and removed credentials
        for edge_id in current_map:
            if edge_id not in baseline_map:
                events.append(DriftEvent(
                    edge_id=edge_id,
                    kind=DriftKind.NEW_CREDENTIAL,
                    baseline_value=None,
                    current_value=edge_id,
                    delta_seconds=None,
                    detected_at=now,
                ))

        for edge_id in baseline_map:
            if edge_id not in current_map:
                events.append(DriftEvent(
                    edge_id=edge_id,
                    kind=DriftKind.REMOVED_CREDENTIAL,
                    baseline_value=edge_id,
                    current_value=None,
                    delta_seconds=None,
                    detected_at=now,
                ))

        # Expiry and staleness drift for edges present in both
        for edge_id in baseline_map:
            if edge_id not in current_map:
                continue
            base_hint = baseline_map[edge_id]
            curr_hint = current_map[edge_id]

            # Expiry drift
            expiry_events = self._compare_expiry(base_hint, curr_hint, now)
            events.extend(expiry_events)

            # Staleness drift
            staleness_events = self._compare_staleness(base_hint, curr_hint, now)
            events.extend(staleness_events)

        return DriftReport(
            events=events,
            detected_at=now,
            baseline_count=len(baseline_map),
            current_count=len(current_map),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _utc(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _compare_expiry(
        self,
        base: TemporalHint,
        curr: TemporalHint,
        now: datetime,
    ) -> list[DriftEvent]:
        if base.credential_expiry is None or curr.credential_expiry is None:
            return []

        base_exp = self._utc(base.credential_expiry)
        curr_exp = self._utc(curr.credential_expiry)
        delta = (curr_exp - base_exp).total_seconds()

        if abs(delta) < self.expiry_threshold:
            return []

        kind = DriftKind.EXPIRY_EXTENDED if delta > 0 else DriftKind.EXPIRY_ADVANCED
        return [DriftEvent(
            edge_id=base.edge_id,
            kind=kind,
            baseline_value=base_exp.isoformat(),
            current_value=curr_exp.isoformat(),
            delta_seconds=delta,
            detected_at=now,
        )]

    def _compare_staleness(
        self,
        base: TemporalHint,
        curr: TemporalHint,
        now: datetime,
    ) -> list[DriftEvent]:
        if base.last_used is None or curr.last_used is None:
            return []

        base_lu = self._utc(base.last_used)
        curr_lu = self._utc(curr.last_used)
        # A more recent last_used means staleness decreased
        delta = (curr_lu - base_lu).total_seconds()

        if abs(delta) < self.staleness_threshold:
            return []

        kind = DriftKind.STALENESS_DECREASED if delta > 0 else DriftKind.STALENESS_INCREASED
        return [DriftEvent(
            edge_id=base.edge_id,
            kind=kind,
            baseline_value=base_lu.isoformat(),
            current_value=curr_lu.isoformat(),
            delta_seconds=delta,
            detected_at=now,
        )]
