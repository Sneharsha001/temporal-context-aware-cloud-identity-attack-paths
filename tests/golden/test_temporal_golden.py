"""
tests/golden/test_temporal_golden.py - Golden tests for the temporal evaluator.

Verifies deterministic verdicts for named reference scenarios. Adding a new
scenario here locks its expected output; any regression will immediately fail.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import pytest

from arf_rt.temporal.config import TemporalConfig
from arf_rt.temporal.evaluator import TemporalEvaluator
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.verdict import VerdictKind


UTC = timezone.utc
BASE = datetime(2025, 6, 15, 8, 0, 0, tzinfo=UTC)


def _dt(offset_seconds: float) -> datetime:
    return BASE + timedelta(seconds=offset_seconds)


def _h(
    eid: str,
    obs_start_s: float | None = None,
    obs_end_s: float | None = None,
    issued_s: float | None = None,
    expiry_s: float | None = None,
    last_used_s: float | None = None,
) -> TemporalHint:
    return TemporalHint(
        edge_id=eid,
        earliest_observed=_dt(obs_start_s) if obs_start_s is not None else None,
        latest_observed=_dt(obs_end_s) if obs_end_s is not None else None,
        credential_issued=_dt(issued_s) if issued_s is not None else None,
        credential_expiry=_dt(expiry_s) if expiry_s is not None else None,
        last_used=_dt(last_used_s) if last_used_s is not None else None,
    )


# ---------------------------------------------------------------------------
# Reference scenarios
# ---------------------------------------------------------------------------


class Scenario(NamedTuple):
    name: str
    edge_ids: list[str]
    hints: dict[str, TemporalHint]
    config: TemporalConfig
    expected_kind: VerdictKind
    expected_constraint: str | None  # None = no violation expected


REF_TIME = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)

SCENARIOS: list[Scenario] = [
    # -------------------------------------------------------------------
    # S1: Two-hop linear path — all clean
    # -------------------------------------------------------------------
    Scenario(
        name="linear_two_hop_clean",
        edge_ids=["e1", "e2"],
        hints={
            "e1": _h("e1", obs_start_s=0, obs_end_s=10, issued_s=0, expiry_s=3600, last_used_s=0),
            "e2": _h("e2", obs_start_s=15, obs_end_s=25, issued_s=15, expiry_s=3615, last_used_s=15),
        },
        config=TemporalConfig(),
        expected_kind=VerdictKind.FEASIBLE,
        expected_constraint=None,
    ),
    # -------------------------------------------------------------------
    # S2: Causal order violation (TC-1)
    # -------------------------------------------------------------------
    Scenario(
        name="causal_order_violation",
        edge_ids=["e1", "e2"],
        hints={
            "e1": _h("e1", obs_start_s=100, obs_end_s=110),
            "e2": _h("e2", obs_start_s=50, obs_end_s=60),   # observed BEFORE e1
        },
        config=TemporalConfig(),
        expected_kind=VerdictKind.INFEASIBLE,
        expected_constraint="TC-1",
    ),
    # -------------------------------------------------------------------
    # S3: Session expiry violation (TC-2)
    # -------------------------------------------------------------------
    Scenario(
        name="session_expiry_violation",
        edge_ids=["e1", "e2"],
        hints={
            "e1": _h("e1", obs_start_s=0, issued_s=0, expiry_s=600),    # expires at +600s
            "e2": _h("e2", obs_start_s=700),                             # observed at +700s
        },
        config=TemporalConfig(session_expiry_grace_seconds=0.0),
        expected_kind=VerdictKind.INFEASIBLE,
        expected_constraint="TC-2",
    ),
    # -------------------------------------------------------------------
    # S4: Sub-second velocity violation (TC-3)
    # -------------------------------------------------------------------
    Scenario(
        name="velocity_violation",
        edge_ids=["e1", "e2"],
        hints={
            "e1": _h("e1", obs_start_s=0, obs_end_s=0),
            "e2": _h("e2", obs_start_s=0),  # same timestamp → 0s gap
        },
        config=TemporalConfig(min_hop_delta_seconds=0.5),
        expected_kind=VerdictKind.INFEASIBLE,
        expected_constraint="TC-3",
    ),
    # -------------------------------------------------------------------
    # S5: Stale credential (TC-4) — last used 100 days ago
    # -------------------------------------------------------------------
    Scenario(
        name="stale_credential",
        edge_ids=["e1"],
        hints={
            "e1": _h("e1", last_used_s=-(100 * 86_400)),  # 100 days before BASE
        },
        config=TemporalConfig(stale_credential_days=90),
        expected_kind=VerdictKind.INFEASIBLE,
        expected_constraint="TC-4",
    ),
    # -------------------------------------------------------------------
    # S6: Concurrent session reuse (TC-5)
    # -------------------------------------------------------------------
    Scenario(
        name="concurrent_session_reuse",
        edge_ids=["e1", "e2"],
        hints={
            "e1": _h("e1", issued_s=0),
            "e2": _h("e2", issued_s=0),  # same issued time
        },
        config=TemporalConfig(enabled_constraints=frozenset({"TC-5"})),
        expected_kind=VerdictKind.INFEASIBLE,
        expected_constraint="TC-5",
    ),
    # -------------------------------------------------------------------
    # S7: All data missing — UNKNOWN with passthrough
    # -------------------------------------------------------------------
    Scenario(
        name="all_unknown_passthrough",
        edge_ids=["e1", "e2"],
        hints={
            "e1": TemporalHint(edge_id="e1"),
            "e2": TemporalHint(edge_id="e2"),
        },
        config=TemporalConfig(unknown_passthrough=True),
        expected_kind=VerdictKind.UNKNOWN,
        expected_constraint=None,
    ),
    # -------------------------------------------------------------------
    # S8: Three-hop diamond with shared session — clean
    # -------------------------------------------------------------------
    Scenario(
        name="three_hop_chain_clean",
        edge_ids=["e1", "e2", "e3"],
        hints={
            "e1": _h("e1", obs_start_s=0, obs_end_s=5, issued_s=0, expiry_s=7200, last_used_s=0),
            "e2": _h("e2", obs_start_s=10, obs_end_s=15, issued_s=10, expiry_s=7210, last_used_s=10),
            "e3": _h("e3", obs_start_s=20, obs_end_s=25, issued_s=20, expiry_s=7220, last_used_s=20),
        },
        config=TemporalConfig(),
        expected_kind=VerdictKind.FEASIBLE,
        expected_constraint=None,
    ),
]


# ---------------------------------------------------------------------------
# Parametrized golden test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_temporal_golden(scenario: Scenario) -> None:
    """Each scenario must produce the locked expected verdict."""
    ev = TemporalEvaluator(config=scenario.config, reference_time=REF_TIME)
    verdict = ev.evaluate(scenario.edge_ids, scenario.hints)

    assert verdict.kind == scenario.expected_kind, (
        f"[{scenario.name}] Expected {scenario.expected_kind.name}, "
        f"got {verdict.kind.name}: {verdict.reason}"
    )
    if scenario.expected_constraint is not None:
        assert verdict.violated_constraint == scenario.expected_constraint, (
            f"[{scenario.name}] Expected violated_constraint={scenario.expected_constraint!r}, "
            f"got {verdict.violated_constraint!r}"
        )
