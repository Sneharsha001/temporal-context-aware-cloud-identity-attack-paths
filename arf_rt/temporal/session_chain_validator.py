"""
arf_rt/temporal/session_chain_validator.py - Transitive STS session chaining validation.

Validates multi-hop AssumeRole session chains against AWS IAM role chaining limits:
  - AWS 1-hour maximum session duration constraint for chained role sessions.
  - Maximum allowable role chaining depth bounds.
  - Monotonic causal issuance constraint across transitive hops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from arf_rt.temporal.hints import TemporalHint


@dataclass(frozen=True)
class ChainViolation:
    """A violation of AWS role chaining or transitive session constraints."""

    hop_index: int
    edge_id: str
    rule: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "hop_index": self.hop_index,
            "edge_id": self.edge_id,
            "rule": self.rule,
            "detail": self.detail,
        }


@dataclass
class ChainValidationResult:
    """Validation report for an identity attack path session chain."""

    path_edges: list[str]
    chain_depth: int
    is_valid: bool
    violations: list[ChainViolation] = field(default_factory=list)
    total_duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "path_edges": self.path_edges,
            "chain_depth": self.chain_depth,
            "is_valid": self.is_valid,
            "violations": [v.to_dict() for v in self.violations],
            "total_duration_seconds": round(self.total_duration_seconds, 2),
        }


class SessionChainValidator:
    """
    Enforces AWS role chaining and transitive session policies.

    Parameters
    ----------
    max_chain_depth:
        Maximum allowed consecutive AssumeRole transitions (default: 4).
    enforce_1hour_chain_rule:
        Whether to enforce AWS's 1-hour (3600s) cap on chained role session durations.
    """

    def __init__(
        self,
        max_chain_depth: int = 4,
        enforce_1hour_chain_rule: bool = True,
    ) -> None:
        self.max_chain_depth = max_chain_depth
        self.enforce_1hour_chain_rule = enforce_1hour_chain_rule

    @staticmethod
    def _utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def validate_chain(
        self,
        path: Sequence[str],
        hints: dict[str, TemporalHint],
    ) -> ChainValidationResult:
        """Validate a sequence of edge IDs forming an identity chain."""
        violations: list[ChainViolation] = []
        path_list = list(path)
        depth = len(path_list)

        # 1. Check max chaining depth
        if depth > self.max_chain_depth:
            violations.append(ChainViolation(
                hop_index=self.max_chain_depth,
                edge_id=path_list[self.max_chain_depth] if self.max_chain_depth < depth else "N/A",
                rule="MAX_CHAIN_DEPTH_EXCEEDED",
                detail=f"Path depth {depth} exceeds maximum role chain limit {self.max_chain_depth}",
            ))

        total_duration = 0.0
        earliest_start: datetime | None = None
        latest_end: datetime | None = None

        prev_issued: datetime | None = None

        for idx, edge_id in enumerate(path_list):
            hint = hints.get(edge_id)
            if hint is None:
                continue

            issued = self._utc(hint.credential_issued)
            expiry = self._utc(hint.credential_expiry)

            # 2. Check monotonic causal issuance
            if issued is not None and prev_issued is not None:
                if issued < prev_issued:
                    violations.append(ChainViolation(
                        hop_index=idx,
                        edge_id=edge_id,
                        rule="CAUSAL_ISSUANCE_INVERSION",
                        detail=f"Hop {idx} credential issued at {issued.isoformat()} before hop {idx-1} at {prev_issued.isoformat()}",
                    ))
            if issued is not None:
                prev_issued = issued

            # 3. AWS Role Chaining 1-hour cap (hops >= 1, i.e., assumed from an already assumed role)
            if idx > 0 and self.enforce_1hour_chain_rule and issued is not None and expiry is not None:
                duration = (expiry - issued).total_seconds()
                if duration > 3600.0:
                    violations.append(ChainViolation(
                        hop_index=idx,
                        edge_id=edge_id,
                        rule="CHAINED_SESSION_DURATION_EXCEEDED",
                        detail=(
                            f"Chained role session duration ({duration:.0f}s) exceeds AWS 1-hour (3600s) maximum"
                        ),
                    ))

            # Track window bounds
            if issued is not None:
                earliest_start = issued if earliest_start is None else min(earliest_start, issued)
            if expiry is not None:
                latest_end = expiry if latest_end is None else max(latest_end, expiry)

        if earliest_start is not None and latest_end is not None:
            total_duration = max(0.0, (latest_end - earliest_start).total_seconds())

        return ChainValidationResult(
            path_edges=path_list,
            chain_depth=depth,
            is_valid=len(violations) == 0,
            violations=violations,
            total_duration_seconds=total_duration,
        )
