"""
arf_rt/temporal/graph_annotator.py - Privilege graph decoration with temporal metadata.

Enriches privilege graph edges with credential validity windows, staleness flags,
and visualization styles (Graphviz/Cytoscape) based on TemporalHint data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from arf_rt.temporal.hints import TemporalHint


@dataclass
class AnnotatedEdge:
    """Represents a graph edge decorated with temporal lifecycle status."""
    source: str
    target: str
    edge_id: str
    hint: TemporalHint | None
    is_stale: bool = False
    is_expired: bool = False
    validity_duration_seconds: float = 0.0
    dot_color: str = "black"
    dot_style: str = "solid"
    attributes: dict[str, Any] = field(default_factory=dict)


class TemporalGraphAnnotator:
    """
    Decorates privilege graph topologies with empirical CloudTrail and STS
    temporal attributes for downstream path visualization and pruning.
    """

    def __init__(
        self,
        hints: dict[str, TemporalHint],
        reference_time: datetime | None = None,
        stale_threshold_days: int = 90,
    ) -> None:
        self.hints = hints
        self.reference_time = reference_time or datetime.now(timezone.utc)
        self.stale_threshold_days = stale_threshold_days

    def annotate_edge(self, source: str, target: str, edge_id: str | None = None) -> AnnotatedEdge:
        """Annotate a single graph edge with temporal metrics and styling."""
        eid = edge_id or f"{source}→{target}"
        hint = self.hints.get(eid)

        is_stale = False
        is_expired = False
        duration = 0.0

        if hint:
            if hint.credential_issued and hint.credential_expiry:
                duration = max(0.0, (hint.credential_expiry - hint.credential_issued).total_seconds())

            if hint.credential_expiry and hint.credential_expiry < self.reference_time:
                is_expired = True

            if hint.last_used:
                days_since_use = (self.reference_time - hint.last_used).total_seconds() / 86400.0
                if days_since_use > self.stale_threshold_days:
                    is_stale = True

        # Determine visual style
        if is_expired:
            color = "red"
            style = "dashed"
        elif is_stale:
            color = "orange"
            style = "dotted"
        elif hint and hint.credential_issued:
            color = "darkgreen"
            style = "bold"
        else:
            color = "gray"
            style = "solid"

        return AnnotatedEdge(
            source=source,
            target=target,
            edge_id=eid,
            hint=hint,
            is_stale=is_stale,
            is_expired=is_expired,
            validity_duration_seconds=duration,
            dot_color=color,
            dot_style=style,
            attributes={
                "label": eid,
                "color": color,
                "style": style,
                "is_expired": str(is_expired),
                "is_stale": str(is_stale),
            },
        )

    def annotate_graph_edges(
        self, edges: list[tuple[str, str] | tuple[str, str, str]]
    ) -> list[AnnotatedEdge]:
        """Annotate a collection of graph edges."""
        annotated: list[AnnotatedEdge] = []
        for e in edges:
            if len(e) == 2:
                annotated.append(self.annotate_edge(e[0], e[1]))
            elif len(e) == 3:
                annotated.append(self.annotate_edge(e[0], e[1], e[2]))
        return annotated
