"""
arf_rt/temporal/correlation_matrix.py - Temporal concurrency and overlap correlation analysis.

Quantifies temporal overlap, window Jaccard similarity, and synchronization
clusters among cloud credentials and privilege edges.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from arf_rt.temporal.hints import TemporalHint


@dataclass(frozen=True)
class PairwiseTemporalOverlap:
    """Temporal correlation and overlap metrics between two credential edges."""

    edge_a: str
    edge_b: str
    overlap_seconds: float
    union_seconds: float
    jaccard_similarity: float
    is_concurrent: bool

    def to_dict(self) -> dict:
        return {
            "edge_a": self.edge_a,
            "edge_b": self.edge_b,
            "overlap_seconds": round(self.overlap_seconds, 2),
            "union_seconds": round(self.union_seconds, 2),
            "jaccard_similarity": round(self.jaccard_similarity, 4),
            "is_concurrent": self.is_concurrent,
        }


class TemporalCorrelationMatrix:
    """
    Computes pairwise temporal intersection and synchronization clusters.
    """

    @staticmethod
    def _utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def compare_pair(
        self,
        hint_a: TemporalHint,
        hint_b: TemporalHint,
    ) -> PairwiseTemporalOverlap:
        """Calculate overlap duration and Jaccard similarity between two hints."""
        # Use credential lifetime window if available; fallback to observation window
        start_a = self._utc(hint_a.credential_issued or hint_a.earliest_observed)
        end_a = self._utc(hint_a.credential_expiry or hint_a.latest_observed)

        start_b = self._utc(hint_b.credential_issued or hint_b.earliest_observed)
        end_b = self._utc(hint_b.credential_expiry or hint_b.latest_observed)

        if not (start_a and end_a and start_b and end_b) or (end_a <= start_a) or (end_b <= start_b):
            return PairwiseTemporalOverlap(
                edge_a=hint_a.edge_id,
                edge_b=hint_b.edge_id,
                overlap_seconds=0.0,
                union_seconds=0.0,
                jaccard_similarity=0.0,
                is_concurrent=False,
            )

        latest_start = max(start_a, start_b)
        earliest_end = min(end_a, end_b)
        overlap_delta = (earliest_end - latest_start).total_seconds()
        overlap = max(0.0, overlap_delta)

        earliest_start = min(start_a, start_b)
        latest_end = max(end_a, end_b)
        union_delta = (latest_end - earliest_start).total_seconds()
        union = max(1e-6, union_delta)

        jaccard = overlap / union if union > 0 else 0.0

        return PairwiseTemporalOverlap(
            edge_a=hint_a.edge_id,
            edge_b=hint_b.edge_id,
            overlap_seconds=overlap,
            union_seconds=union,
            jaccard_similarity=jaccard,
            is_concurrent=overlap > 0.0,
        )

    def compute_matrix(
        self,
        hints: Sequence[TemporalHint],
    ) -> dict[tuple[str, str], PairwiseTemporalOverlap]:
        """Compute all pairwise overlap metrics."""
        result: dict[tuple[str, str], PairwiseTemporalOverlap] = {}
        hint_list = list(hints)
        n = len(hint_list)

        for i in range(n):
            for j in range(i + 1, n):
                ha = hint_list[i]
                hb = hint_list[j]
                overlap = self.compare_pair(ha, hb)
                result[(ha.edge_id, hb.edge_id)] = overlap
                # Symmetric entry
                result[(hb.edge_id, ha.edge_id)] = PairwiseTemporalOverlap(
                    edge_a=hb.edge_id,
                    edge_b=ha.edge_id,
                    overlap_seconds=overlap.overlap_seconds,
                    union_seconds=overlap.union_seconds,
                    jaccard_similarity=overlap.jaccard_similarity,
                    is_concurrent=overlap.is_concurrent,
                )
        return result

    def find_concurrent_pairs(
        self,
        hints: Sequence[TemporalHint],
        min_overlap_seconds: float = 0.0,
    ) -> list[PairwiseTemporalOverlap]:
        """Return distinct pairs of credentials with active concurrent validity."""
        hint_list = list(hints)
        n = len(hint_list)
        concurrent: list[PairwiseTemporalOverlap] = []

        for i in range(n):
            for j in range(i + 1, n):
                ov = self.compare_pair(hint_list[i], hint_list[j])
                if ov.overlap_seconds > min_overlap_seconds:
                    concurrent.append(ov)
        return sorted(concurrent, key=lambda x: x.overlap_seconds, reverse=True)

    def find_synchronized_clusters(
        self,
        hints: Sequence[TemporalHint],
        min_jaccard: float = 0.85,
    ) -> list[list[str]]:
        """
        Group credentials that share highly synchronized validity windows (e.g. batch rotation).
        Uses connected-component clustering.
        """
        valid_hints = [
            h for h in hints
            if (h.credential_issued and h.credential_expiry) or (h.earliest_observed and h.latest_observed)
        ]
        edge_ids = [h.edge_id for h in valid_hints]
        adj: dict[str, set[str]] = {eid: set() for eid in edge_ids}

        n = len(valid_hints)
        for i in range(n):
            for j in range(i + 1, n):
                ha = valid_hints[i]
                hb = valid_hints[j]
                ov = self.compare_pair(ha, hb)
                if ov.jaccard_similarity >= min_jaccard:
                    adj[ha.edge_id].add(hb.edge_id)
                    adj[hb.edge_id].add(ha.edge_id)

        visited: set[str] = set()
        clusters: list[list[str]] = []

        for eid in edge_ids:
            if eid not in visited:
                comp: list[str] = []
                queue = [eid]
                visited.add(eid)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                if len(comp) > 1:
                    clusters.append(sorted(comp))

        return sorted(clusters, key=lambda c: len(c), reverse=True)
