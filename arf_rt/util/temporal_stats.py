"""
arf_rt/util/temporal_stats.py - Statistical analysis helpers for temporal event sequences.

Calculates inter-arrival durations, event burst metrics, dispersion statistics,
and detects temporal distribution outliers for cloud identity attack paths.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


def compute_inter_arrival_times(timestamps: list[datetime]) -> list[float]:
    """
    Calculate the elapsed seconds between consecutive sorted timestamps.
    Returns an empty list if fewer than 2 timestamps are provided.
    """
    if len(timestamps) < 2:
        return []

    sorted_ts = sorted(timestamps)
    return [
        (sorted_ts[i + 1] - sorted_ts[i]).total_seconds()
        for i in range(len(sorted_ts) - 1)
    ]


def compute_duration_statistics(durations: list[float]) -> dict[str, float]:
    """
    Compute descriptive statistics for a sequence of durations (in seconds).
    Returns dict with min, max, mean, median, stddev, and count.
    """
    if not durations:
        return {
            "count": 0.0,
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "stddev": 0.0,
        }

    n = len(durations)
    s_durations = sorted(durations)
    mean_val = sum(durations) / n

    if n % 2 == 1:
        median_val = s_durations[n // 2]
    else:
        median_val = (s_durations[n // 2 - 1] + s_durations[n // 2]) / 2.0

    variance = sum((x - mean_val) ** 2 for x in durations) / n
    stddev_val = math.sqrt(variance)

    return {
        "count": float(n),
        "min": float(s_durations[0]),
        "max": float(s_durations[-1]),
        "mean": round(mean_val, 4),
        "median": round(median_val, 4),
        "stddev": round(stddev_val, 4),
    }


def detect_timing_outliers(
    durations: list[float], threshold_z_score: float = 3.0
) -> list[int]:
    """
    Identifies index positions of duration outliers exceeding the given z-score threshold.
    """
    if len(durations) < 3:
        return []

    stats = compute_duration_statistics(durations)
    stddev = stats["stddev"]
    mean = stats["mean"]

    if stddev == 0.0:
        return []

    outliers: list[int] = []
    for idx, d in enumerate(durations):
        z = abs(d - mean) / stddev
        if z >= threshold_z_score:
            outliers.append(idx)

    return outliers
