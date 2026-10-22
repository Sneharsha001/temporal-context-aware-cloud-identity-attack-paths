"""
arf_rt/temporal/audit_log.py - Structured audit log for temporal evaluation decisions.

Records each TemporalVerdict with its context (path, constraint, timestamp)
so that decisions can be reviewed, replayed, or exported for incident response.

The log is an in-memory append-only list by default. Call ``to_jsonl()`` to
serialize to newline-delimited JSON for writing to disk or S3.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Iterator

from arf_rt.temporal.verdict import TemporalVerdict, VerdictKind


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class AuditEntry:
    """
    A single recorded temporal evaluation decision.

    Attributes
    ----------
    logged_at:
        UTC ISO-8601 timestamp of when the verdict was recorded.
    path_edge_ids:
        Ordered edge IDs of the evaluated path.
    verdict_kind:
        String name of VerdictKind (FEASIBLE / INFEASIBLE / UNKNOWN).
    violated_constraint:
        Constraint ID that caused INFEASIBLE, or None.
    reason:
        Human-readable verdict explanation.
    missing_data_constraints:
        Constraints that lacked data (relevant for UNKNOWN).
    metadata:
        Arbitrary key-value pairs for caller-supplied context (scenario ID, etc.).
    """

    logged_at: str
    path_edge_ids: list[str]
    verdict_kind: str
    violated_constraint: str | None
    reason: str
    missing_data_constraints: list[str]
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class TemporalAuditLog:
    """
    In-memory append-only audit log for temporal evaluation decisions.

    Usage::

        log = TemporalAuditLog()
        verdict = evaluator.evaluate(path, hints)
        log.record(path, verdict, metadata={"scenario": "s1"})

        for entry in log:
            print(entry.to_json())

        log.write_jsonl(Path("temporal_audit.jsonl"))
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(
        self,
        path_edge_ids: list[str],
        verdict: TemporalVerdict,
        metadata: dict[str, str] | None = None,
    ) -> AuditEntry:
        """
        Record a temporal verdict and return the created AuditEntry.

        Parameters
        ----------
        path_edge_ids:
            The ordered edge IDs of the evaluated path.
        verdict:
            The TemporalVerdict returned by the evaluator.
        metadata:
            Optional caller-supplied key-value context.
        """
        entry = AuditEntry(
            logged_at=_now_iso(),
            path_edge_ids=list(path_edge_ids),
            verdict_kind=verdict.kind.name,
            violated_constraint=verdict.violated_constraint,
            reason=verdict.reason,
            missing_data_constraints=sorted(verdict.missing_data_constraints),
            metadata=dict(metadata or {}),
        )
        self._entries.append(entry)
        return entry

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[AuditEntry]:
        return iter(self._entries)

    @property
    def entries(self) -> list[AuditEntry]:
        """Return a copy of all recorded audit entries."""
        return list(self._entries)

    def entries_by_kind(self, kind: VerdictKind) -> list[AuditEntry]:
        """Return all entries matching the given verdict kind."""
        return [e for e in self._entries if e.verdict_kind == kind.name]

    def infeasible_entries(self) -> list[AuditEntry]:
        return self.entries_by_kind(VerdictKind.INFEASIBLE)

    def unknown_entries(self) -> list[AuditEntry]:
        return self.entries_by_kind(VerdictKind.UNKNOWN)

    def feasible_entries(self) -> list[AuditEntry]:
        return self.entries_by_kind(VerdictKind.FEASIBLE)

    def to_jsonl(self) -> str:
        """Serialize all entries to newline-delimited JSON."""
        return "\n".join(e.to_json() for e in self._entries)

    def write_jsonl(self, path: "Path") -> None:  # type: ignore[name-defined]
        """Write all entries to a JSONL file at ``path``."""
        from pathlib import Path as _Path
        _Path(path).write_text(self.to_jsonl(), encoding="utf-8")

    def clear(self) -> None:
        """Remove all recorded entries (useful between test runs)."""
        self._entries.clear()

    def summary(self) -> dict[str, int]:
        """Return counts per verdict kind."""
        return {
            "FEASIBLE": len(self.feasible_entries()),
            "INFEASIBLE": len(self.infeasible_entries()),
            "UNKNOWN": len(self.unknown_entries()),
            "total": len(self),
        }
