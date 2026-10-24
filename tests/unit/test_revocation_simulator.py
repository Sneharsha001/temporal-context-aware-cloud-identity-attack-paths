"""
tests/unit/test_revocation_simulator.py - Unit tests for SessionRevocationSimulator.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.revocation_simulator import SessionRevocationSimulator


@pytest.fixture
def revocation_fixtures() -> tuple[list[list[str]], dict[str, TemporalHint], datetime]:
    utc = timezone.utc
    base_time = datetime(2026, 10, 24, 10, 0, 0, tzinfo=utc)

    # Hop 1: occurred at 10:00 (before revocation)
    h1 = TemporalHint(
        edge_id="user→roleA",
        earliest_observed=base_time,
        credential_issued=base_time,
    )
    # Hop 2: occurred at 10:30 (after revocation at 10:15)
    h2 = TemporalHint(
        edge_id="roleA→roleB",
        earliest_observed=base_time + timedelta(minutes=30),
        credential_issued=base_time + timedelta(minutes=30),
    )
    # Hop 3: independent role C at 10:05
    h3 = TemporalHint(
        edge_id="user→roleC",
        earliest_observed=base_time + timedelta(minutes=5),
        credential_issued=base_time + timedelta(minutes=5),
    )

    paths = [
        ["user→roleA", "roleA→roleB"],   # Path 1: contains roleA used after revocation
        ["user→roleC"],                   # Path 2: independent path
    ]
    hints = {
        "user→roleA": h1,
        "roleA→roleB": h2,
        "user→roleC": h3,
    }
    return paths, hints, base_time


class TestSessionRevocationSimulator:
    def test_revocation_severing(
        self, revocation_fixtures: tuple[list[list[str]], dict[str, TemporalHint], datetime]
    ) -> None:
        paths, hints, base_time = revocation_fixtures
        revocation_time = base_time + timedelta(minutes=15)  # 10:15

        impact = SessionRevocationSimulator.simulate_revocation(
            paths=paths,
            hints=hints,
            revocation_time=revocation_time,
            revoked_edge_or_role_identifiers={"roleA"},
        )

        assert impact.total_paths == 2
        assert impact.eliminated_paths_count == 1
        assert impact.active_paths_count == 1
        assert impact.elimination_ratio == 0.5
        assert impact.severed_paths == [["user→roleA", "roleA→roleB"]]
        assert impact.remaining_paths == [["user→roleC"]]

    def test_revocation_before_any_events(
        self, revocation_fixtures: tuple[list[list[str]], dict[str, TemporalHint], datetime]
    ) -> None:
        paths, hints, base_time = revocation_fixtures
        # Revoke everything from 09:00
        revocation_time = base_time - timedelta(hours=1)

        impact = SessionRevocationSimulator.simulate_revocation(
            paths=paths,
            hints=hints,
            revocation_time=revocation_time,
            revoked_edge_or_role_identifiers={"roleA", "roleC"},
        )

        assert impact.eliminated_paths_count == 2
        assert impact.elimination_ratio == 1.0
        assert impact.active_paths_count == 0

    def test_no_matching_revocations(
        self, revocation_fixtures: tuple[list[list[str]], dict[str, TemporalHint], datetime]
    ) -> None:
        paths, hints, base_time = revocation_fixtures
        impact = SessionRevocationSimulator.simulate_revocation(
            paths=paths,
            hints=hints,
            revocation_time=base_time,
            revoked_edge_or_role_identifiers={"roleUnrelated"},
        )

        assert impact.eliminated_paths_count == 0
        assert impact.elimination_ratio == 0.0
        assert impact.active_paths_count == 2
