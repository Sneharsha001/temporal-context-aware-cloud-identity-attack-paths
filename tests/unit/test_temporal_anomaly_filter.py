"""
tests/unit/test_temporal_anomaly_filter.py - Tests for TemporalAnomalyFilter.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from arf_rt.temporal.anomaly_classifier import ClassifiedAnomaly, SeverityTier
from arf_rt.temporal.anomaly_filter import (
    MaintenanceWindow,
    TemporalAnomalyFilter,
)


UTC = timezone.utc


class TestTemporalAnomalyFilter:
    def test_maintenance_window_contains(self) -> None:
        t0 = datetime(2025, 6, 15, 2, 0, 0, tzinfo=UTC)
        t1 = datetime(2025, 6, 15, 4, 0, 0, tzinfo=UTC)
        mw = MaintenanceWindow(start=t0, end=t1, description="Nightly DB maintenance")

        inside = datetime(2025, 6, 15, 3, 0, 0, tzinfo=UTC)
        outside_before = datetime(2025, 6, 15, 1, 59, 0, tzinfo=UTC)
        outside_after = datetime(2025, 6, 15, 4, 1, 0, tzinfo=UTC)

        assert mw.contains(inside) is True
        assert mw.contains(outside_before) is False
        assert mw.contains(outside_after) is False

    def test_maintenance_window_invalid_bounds(self) -> None:
        t0 = datetime(2025, 6, 15, 4, 0, 0, tzinfo=UTC)
        t1 = datetime(2025, 6, 15, 2, 0, 0, tzinfo=UTC)
        with pytest.raises(ValueError, match="must be after start"):
            MaintenanceWindow(start=t0, end=t1)

    def test_suppression_of_anomalies_in_window(self) -> None:
        t0 = datetime(2025, 6, 15, 2, 0, 0, tzinfo=UTC)
        t1 = datetime(2025, 6, 15, 4, 0, 0, tzinfo=UTC)
        mw = MaintenanceWindow(start=t0, end=t1, description="Patch window")
        f = TemporalAnomalyFilter(maintenance_windows=[mw])

        anomaly_in = ClassifiedAnomaly(
            anomaly_id="TC-1",
            severity=SeverityTier.HIGH,
            title="Test anomaly in window",
            description="High velocity",
            remediation="Review",
        )
        anomaly_out = ClassifiedAnomaly(
            anomaly_id="TC-4",
            severity=SeverityTier.HIGH,
            title="Test anomaly outside window",
            description="Stale credential",
            remediation="Rotate",
        )

        timestamps = {
            "TC-1": datetime(2025, 6, 15, 3, 0, 0, tzinfo=UTC),
            "TC-4": datetime(2025, 6, 15, 8, 0, 0, tzinfo=UTC),
        }

        results = f.filter_anomalies([anomaly_in, anomaly_out], timestamps)
        assert len(results) == 2

        assert results[0].is_suppressed is True
        assert "Patch window" in results[0].suppression_reason

        assert results[1].is_suppressed is False
        assert results[1].suppression_reason == ""

    def test_compute_z_scores_and_outlier_detection(self) -> None:
        durations = [10.0, 10.2, 9.8, 10.1, 9.9, 10.0, 10.3, 100.0]  # 100.0 is an extreme outlier
        f = TemporalAnomalyFilter(z_score_threshold=2.0)
        outliers = f.detect_velocity_outliers(durations)

        assert len(outliers) == 8
        assert outliers[-1] is True  # 100.0 flagged as outlier
        assert all(not o for o in outliers[:-1])  # normal values not flagged

    def test_empty_and_single_element_z_scores(self) -> None:
        assert TemporalAnomalyFilter.compute_z_scores([]) == []
        assert TemporalAnomalyFilter.compute_z_scores([5.0]) == [0.0]
        assert TemporalAnomalyFilter.compute_z_scores([5.0, 5.0, 5.0]) == [0.0, 0.0, 0.0]
