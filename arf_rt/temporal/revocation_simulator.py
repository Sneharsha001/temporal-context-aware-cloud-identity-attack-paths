"""
arf_rt/temporal/revocation_simulator.py - Incident response blast radius simulator.

Simulates the impact of credential revocation actions (e.g. AWS RevokeOlderSessions
or inline Deny attachments) on candidate attack paths, quantifying risk reduction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from arf_rt.temporal.hints import TemporalHint


@dataclass
class RevocationImpact:
    """Quantitative impact of a simulated credential revocation."""
    total_paths: int
    eliminated_paths_count: int
    active_paths_count: int
    elimination_ratio: float
    severed_paths: list[list[str]] = field(default_factory=list)
    remaining_paths: list[list[str]] = field(default_factory=list)


class SessionRevocationSimulator:
    """
    Simulates remediation actions to measure how many attack paths are
    neutralized when specific IAM roles or session credentials are invalidated.
    """

    @classmethod
    def simulate_revocation(
        cls,
        paths: list[list[str]],
        hints: dict[str, TemporalHint],
        revocation_time: datetime,
        revoked_edge_or_role_identifiers: set[str],
    ) -> RevocationImpact:
        """
        Evaluate candidate paths against a hypothetical revocation timestamp.

        Any hop matching the revoked identifier whose activity or credential issuance
        occurs after `revocation_time` is treated as revoked/severed.
        """
        severed: list[list[str]] = []
        remaining: list[list[str]] = []

        for path in paths:
            is_severed = False
            for edge_id in path:
                # Check if this edge or its roles are targeted
                matches = any(
                    ident in edge_id for ident in revoked_edge_or_role_identifiers
                )
                if matches:
                    hint = hints.get(edge_id)
                    # If action occurred or credential issued after revocation_time, it is blocked
                    if hint:
                        obs = hint.earliest_observed or hint.credential_issued
                        if obs and obs >= revocation_time:
                            is_severed = True
                            break
                    else:
                        # Without timestamp, fail closed under proactive revocation
                        is_severed = True
                        break

            if is_severed:
                severed.append(path)
            else:
                remaining.append(path)

        total = len(paths)
        elim_count = len(severed)
        ratio = elim_count / max(1, total)

        return RevocationImpact(
            total_paths=total,
            eliminated_paths_count=elim_count,
            active_paths_count=len(remaining),
            elimination_ratio=ratio,
            severed_paths=severed,
            remaining_paths=remaining,
        )
