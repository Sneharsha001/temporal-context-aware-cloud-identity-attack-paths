"""
arf_rt/temporal/temporal_exporter.py - Multi-format export for temporal analysis results.

Serializes CredentialRiskScore lists, TemporalHint collections, and path feasibility
summaries to JSON, newline-delimited JSON (NDJSON), and CSV formats suitable for
SIEM ingestion, offline analysis, and dashboard integration.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from arf_rt.temporal.credential_scorer import CredentialRiskScore
from arf_rt.temporal.hints import TemporalHint


# ---------------------------------------------------------------------------
# Export record types
# ---------------------------------------------------------------------------

@dataclass
class HintExportRecord:
    """Flat, serialisable representation of a TemporalHint."""

    edge_id: str
    earliest_observed: str | None
    latest_observed: str | None
    credential_issued: str | None
    credential_expiry: str | None
    last_used: str | None

    @classmethod
    def from_hint(cls, hint: TemporalHint) -> "HintExportRecord":
        def _fmt(dt: datetime | None) -> str | None:
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()

        return cls(
            edge_id=hint.edge_id,
            earliest_observed=_fmt(hint.earliest_observed),
            latest_observed=_fmt(hint.latest_observed),
            credential_issued=_fmt(hint.credential_issued),
            credential_expiry=_fmt(hint.credential_expiry),
            last_used=_fmt(hint.last_used),
        )


@dataclass
class ScoreExportRecord:
    """Flat, serialisable representation of a CredentialRiskScore."""

    edge_id: str
    score: float
    label: str
    expiry_factor: float
    staleness_factor: float
    short_lived_bonus: float


# ---------------------------------------------------------------------------
# Exporter
# ---------------------------------------------------------------------------

class TemporalExporter:
    """
    Converts temporal analysis artefacts to portable export formats.

    All methods return a string containing the formatted output.
    """

    # ------------------------------------------------------------------
    # Hint exports
    # ------------------------------------------------------------------

    def hints_to_json(
        self,
        hints: Sequence[TemporalHint],
        *,
        indent: int = 2,
    ) -> str:
        """Serialise a list of hints to a pretty-printed JSON array."""
        records = [asdict(HintExportRecord.from_hint(h)) for h in hints]
        return json.dumps(records, indent=indent, default=str)

    def hints_to_ndjson(self, hints: Sequence[TemporalHint]) -> str:
        """Serialise hints as newline-delimited JSON (one object per line)."""
        lines = [
            json.dumps(asdict(HintExportRecord.from_hint(h)), default=str)
            for h in hints
        ]
        return "\n".join(lines)

    def hints_to_csv(self, hints: Sequence[TemporalHint]) -> str:
        """Serialise hints as a CSV string with a header row."""
        buf = io.StringIO()
        fields = [
            "edge_id",
            "earliest_observed",
            "latest_observed",
            "credential_issued",
            "credential_expiry",
            "last_used",
        ]
        writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for h in hints:
            rec = HintExportRecord.from_hint(h)
            writer.writerow(asdict(rec))
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Score exports
    # ------------------------------------------------------------------

    def scores_to_json(
        self,
        scores: Sequence[CredentialRiskScore],
        *,
        indent: int = 2,
    ) -> str:
        """Serialise risk scores to a pretty-printed JSON array."""
        records = [
            ScoreExportRecord(
                edge_id=s.edge_id,
                score=s.score,
                label=s.label,
                expiry_factor=s.expiry_factor,
                staleness_factor=s.staleness_factor,
                short_lived_bonus=s.short_lived_bonus,
            )
            for s in scores
        ]
        return json.dumps([asdict(r) for r in records], indent=indent)

    def scores_to_ndjson(self, scores: Sequence[CredentialRiskScore]) -> str:
        """Serialise risk scores as newline-delimited JSON."""
        lines = [
            json.dumps({
                "edge_id": s.edge_id,
                "score": s.score,
                "label": s.label,
                "expiry_factor": s.expiry_factor,
                "staleness_factor": s.staleness_factor,
                "short_lived_bonus": s.short_lived_bonus,
            })
            for s in scores
        ]
        return "\n".join(lines)

    def scores_to_csv(self, scores: Sequence[CredentialRiskScore]) -> str:
        """Serialise risk scores as a CSV string with a header row."""
        buf = io.StringIO()
        fields = [
            "edge_id",
            "score",
            "label",
            "expiry_factor",
            "staleness_factor",
            "short_lived_bonus",
        ]
        writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for s in scores:
            writer.writerow({
                "edge_id": s.edge_id,
                "score": s.score,
                "label": s.label,
                "expiry_factor": s.expiry_factor,
                "staleness_factor": s.staleness_factor,
                "short_lived_bonus": s.short_lived_bonus,
            })
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Combined summary
    # ------------------------------------------------------------------

    def summary_json(
        self,
        hints: Sequence[TemporalHint],
        scores: Sequence[CredentialRiskScore],
        *,
        generated_at: datetime | None = None,
    ) -> str:
        """
        Export a combined JSON summary containing metadata, hint records,
        and risk score records. Suitable for report archiving.
        """
        ts = generated_at or datetime.now(tz=timezone.utc)
        payload: dict[str, Any] = {
            "generated_at": ts.isoformat(),
            "hint_count": len(hints),
            "score_count": len(scores),
            "hints": json.loads(self.hints_to_json(hints)),
            "scores": json.loads(self.scores_to_json(scores)),
        }
        return json.dumps(payload, indent=2, default=str)
