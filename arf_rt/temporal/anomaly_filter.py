"""
arf_rt/temporal/anomaly_filter.py - Statistical anomaly filtering and maintenance window suppression.

Filters temporal anomalies using statistical z-score outlier bounds and suppresses
expected alerts that occur during approved maintenance windows.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from arf_rt.temporal.anomaly_classifier import ClassifiedAnomaly


@dataclass(frozen=True)
class MaintenanceWindow:
    """An approved maintenance window during which anomalies are suppressed."""

    start: datetime
    end: datetime
    description: str = ""

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"MaintenanceWindow end ({self.end}) must be after start ({self.start})")

    def contains(self, timestamp: datetime) -> bool:
        t = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
        s = self.start if self.start.tzinfo else self.start.replace(tzinfo=timezone.utc)
        e = self.end if self.end.tzinfo else self.end.replace(tzinfo=timezone.utc)
        return s <= t <= e


@dataclass
class FilteredAnomaly:
    """An anomaly record with filtering status and rationale."""

    anomaly: ClassifiedAnomaly
    is_suppressed: bool
    suppression_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "anomaly": self.anomaly.to_dict(),
            "is_suppressed": self.is_suppressed,
            "suppression_reason": self.suppression_reason,
        }


class TemporalAnomalyFilter:
    """
    Applies statistical z-score filtering and maintenance window suppression.

    Parameters
    ----------
    maintenance_windows:
        List of approved operational maintenance windows.
    z_score_threshold:
        Standard deviations threshold for statistical anomaly classification (default: 3.0).
    """

    def __init__(
        self,
        maintenance_windows: Sequence[MaintenanceWindow] | None = None,
        z_score_threshold: float = 3.0,
    ) -> None:
        self.maintenance_windows = list(maintenance_windows or [])
        self.z_score_threshold = z_score_threshold

    def is_in_maintenance_window(self, timestamp: datetime) -> tuple[bool, str]:
        """Check if a timestamp falls within any registered maintenance window."""
        for mw in self.maintenance_windows:
            if mw.contains(timestamp):
                desc = mw.description or f"Window [{mw.start.isoformat()} - {mw.end.isoformat()}]"
                return True, desc
        return False, ""

    def filter_anomalies(
        self,
        anomalies: Sequence[ClassifiedAnomaly],
        event_timestamps: dict[str, datetime] | None = None,
    ) -> list[FilteredAnomaly]:
        """
        Evaluate anomalies and mark those falling into maintenance windows as suppressed.
        """
        timestamps = event_timestamps or {}
        results: list[FilteredAnomaly] = []

        for a in anomalies:
            ts = timestamps.get(a.edge_id)
            if ts is not None:
                in_mw, reason = self.is_in_maintenance_window(ts)
                if in_mw:
                    results.append(FilteredAnomaly(
                        anomaly=a,
                        is_suppressed=True,
                        suppression_reason=f"Approved Maintenance Window: {reason}",
                    ))
                    continue

            results.append(FilteredAnomaly(
                anomaly=a,
                is_suppressed=False,
                suppression_reason="",
            ))
        return results

    @staticmethod
    def compute_z_scores(values: Sequence[float]) -> list[float]:
        """Calculate standard z-scores for a sequence of observations."""
        n = len(values)
        if n < 2:
            return [0.0] * n

        mean = sum(values) / n
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        std_dev = math.sqrt(variance)

        if std_dev == 0.0:
            return [0.0] * n

        return [(x - mean) / std_dev for x in values]

    def detect_velocity_outliers(
        self,
        hop_durations: Sequence[float],
    ) -> list[bool]:
        """
        Identify values exceeding z_score_threshold (True = statistical outlier).
        """
        z_scores = self.compute_z_scores(hop_durations)
        return [abs(z) > self.z_score_threshold for z in z_scores]
