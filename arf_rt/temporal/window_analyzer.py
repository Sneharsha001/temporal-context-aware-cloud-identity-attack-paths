"""
arf_rt/temporal/window_analyzer.py - Temporal window analysis utilities.

Provides helpers for detecting suspicious timing patterns in multi-hop
attack paths:

- Impossible concurrency (two hops completing in sub-human time)
- Session reuse across distinct account boundaries
- Burst detection (N hops in a sliding time window)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from arf_rt.temporal.hints import TemporalHint


@dataclass(frozen=True)
class WindowAnalysisResult:
    """Result of a timing-window analysis over a path."""

    suspicious: bool
    reason: str
    affected_edge_ids: tuple[str, ...]

    @classmethod
    def clean(cls) -> "WindowAnalysisResult":
        return cls(suspicious=False, reason="No anomalous timing detected.", affected_edge_ids=())

    @classmethod
    def anomaly(cls, reason: str, affected: tuple[str, ...]) -> "WindowAnalysisResult":
        return cls(suspicious=True, reason=reason, affected_edge_ids=affected)


def detect_impossible_concurrency(
    path: list[TemporalHint],
    min_human_latency_seconds: float = 2.0,
) -> WindowAnalysisResult:
    """
    Flag paths where consecutive hops complete faster than realistic human
    latency, suggesting automated tooling or API-level chaining.

    Parameters
    ----------
    path:
        Ordered list of TemporalHints for the path.
    min_human_latency_seconds:
        Minimum expected latency for a human-driven hop (default: 2s).

    Returns
    -------
    WindowAnalysisResult
    """
    for i in range(1, len(path)):
        prev = path[i - 1]
        curr = path[i]
        if prev.latest_observed is None or curr.earliest_observed is None:
            continue
        delta = (curr.earliest_observed - prev.latest_observed).total_seconds()
        if 0 <= delta < min_human_latency_seconds:
            return WindowAnalysisResult.anomaly(
                reason=(
                    f"Hops {prev.edge_id!r} → {curr.edge_id!r} separated by only "
                    f"{delta:.3f}s (below human latency threshold of "
                    f"{min_human_latency_seconds}s)."
                ),
                affected=(prev.edge_id, curr.edge_id),
            )
    return WindowAnalysisResult.clean()


def detect_burst(
    path: list[TemporalHint],
    window_seconds: float = 60.0,
    max_hops_in_window: int = 5,
) -> WindowAnalysisResult:
    """
    Flag paths where more than ``max_hops_in_window`` hops occur within
    a sliding window of ``window_seconds``.

    Parameters
    ----------
    path:
        Ordered list of TemporalHints for the path.
    window_seconds:
        Sliding window length in seconds.
    max_hops_in_window:
        Maximum allowed hops in the window before flagging.

    Returns
    -------
    WindowAnalysisResult
    """
    timestamps: list[tuple[datetime, str]] = [
        (h.earliest_observed, h.edge_id)
        for h in path
        if h.earliest_observed is not None
    ]
    timestamps.sort(key=lambda x: x[0])

    window = timedelta(seconds=window_seconds)
    left = 0
    for right in range(len(timestamps)):
        while timestamps[right][0] - timestamps[left][0] > window:
            left += 1
        count = right - left + 1
        if count > max_hops_in_window:
            affected = tuple(t[1] for t in timestamps[left : right + 1])
            return WindowAnalysisResult.anomaly(
                reason=(
                    f"{count} hops occurred within {window_seconds}s window "
                    f"(threshold: {max_hops_in_window})."
                ),
                affected=affected,
            )
    return WindowAnalysisResult.clean()


def detect_cross_account_reuse(
    path: list[TemporalHint],
) -> WindowAnalysisResult:
    """
    Detect when the same credential_issued timestamp appears on hops that
    cross account boundaries (inferred from edge IDs containing different
    AWS account IDs).

    This is a heuristic — it requires edge IDs to embed ARN fragments that
    include the 12-digit account ID.
    """
    import re

    account_re = re.compile(r":(\d{12}):")

    issued_to_accounts: dict[float, set[str]] = {}
    issued_to_edges: dict[float, list[str]] = {}

    for hint in path:
        if hint.credential_issued is None:
            continue
        key = hint.credential_issued.timestamp()
        accounts = set(account_re.findall(hint.edge_id))
        issued_to_accounts.setdefault(key, set()).update(accounts)
        issued_to_edges.setdefault(key, []).append(hint.edge_id)

    for key, accounts in issued_to_accounts.items():
        if len(accounts) > 1:
            affected = tuple(issued_to_edges[key])
            return WindowAnalysisResult.anomaly(
                reason=(
                    f"Single credential (issued at key={key}) appears across "
                    f"{len(accounts)} distinct AWS accounts: {sorted(accounts)}."
                ),
                affected=affected,
            )
    return WindowAnalysisResult.clean()
