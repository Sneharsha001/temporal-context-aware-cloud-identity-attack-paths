"""Tests for engine/updater.py (spec §§9-11)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arf_rt.adapters.replay import ReplayAdapter
from arf_rt.adapters.seed_json import load_scenario_file
from arf_rt.engine.updater import apply_all_observations, apply_observation
from arf_rt.storage.sqlite_store import connect


FIXTURES = Path(__file__).parent.parent / "fixtures"
MINIMAL = FIXTURES / "minimal_scenario.json"


def _setup_minimal():
    """Ingest minimal scenario, return conn."""
    conn = connect(":memory:")
    scenario = load_scenario_file(MINIMAL)
    adapter = ReplayAdapter(conn)
    adapter.ingest(scenario)
    return conn


def _get_edge(conn, edge_id):
    return conn.execute(
        "SELECT * FROM edges WHERE edge_id = ?", (edge_id,)
    ).fetchone()


def _get_edge_ids(conn):
    rows = conn.execute(
        "SELECT edge_id FROM edges ORDER BY edge_id COLLATE BINARY"
    ).fetchall()
    return [r["edge_id"] for r in rows]


class TestApplyAllObservations:
    """Test the full observation application pipeline."""

    def test_applies_all_three_observations(self) -> None:
        conn = _setup_minimal()
        results = apply_all_observations(conn)
        assert len(results) == 3

    def test_first_obs_allow_updates_alpha(self) -> None:
        """Obs 1: ALLOW on A→B, DIRECT, signal_q=80."""
        conn = _setup_minimal()
        results = apply_all_observations(conn)

        r = results[0]
        assert r["polarity"] == "SUPPORT"
        # inc = floor(95 * 80 / 100) = 76
        assert r["increment"] == 76
        # alpha starts at 1, becomes 1 + 76 = 77
        assert r["alpha_before"] == 1
        assert r["alpha_after"] == 77
        assert r["beta_before"] == 1
        assert r["beta_after"] == 1

    def test_second_obs_deny_updates_beta(self) -> None:
        """Obs 2: DENY+CONSTRAINT_DENY on B→C, DIRECT, signal_q=90."""
        conn = _setup_minimal()
        results = apply_all_observations(conn)

        r = results[1]
        assert r["polarity"] == "AGAINST"
        # inc = floor(95 * 90 / 100) = 85
        assert r["increment"] == 85
        assert r["beta_after"] == 1 + 85  # = 86
        assert r["alpha_after"] == 1  # unchanged

    def test_third_obs_downgraded_inferred(self) -> None:
        """Obs 3: ALLOW on A→B, was DIRECT→INFERRED (no evidence_hash), signal_q=70."""
        conn = _setup_minimal()
        results = apply_all_observations(conn)

        r = results[2]
        assert r["polarity"] == "SUPPORT"
        # INFERRED base_w_q = 60, inc = floor(60 * 70 / 100) = 42
        assert r["increment"] == 42
        # alpha was 77 from first obs, now 77 + 42 = 119
        assert r["alpha_before"] == 77
        assert r["alpha_after"] == 119

    def test_edge_state_after_all_obs(self) -> None:
        """Check final edge state in DB after all observations applied."""
        conn = _setup_minimal()
        apply_all_observations(conn)

        edge_ids = _get_edge_ids(conn)

        # Find edge A→B (has obs 1 and 3)
        for eid in edge_ids:
            e = _get_edge(conn, eid)
            if e["status"] == "CONFIRMED":
                # A→B: alpha=119, beta=1
                assert e["alpha_i"] == 119
                assert e["beta_i"] == 1
                flags = json.loads(e["flags_json"])
                assert flags["prior_only"] is False
                break

    def test_prior_only_cleared(self) -> None:
        """After observations, prior_only should be False."""
        conn = _setup_minimal()
        apply_all_observations(conn)

        rows = conn.execute("SELECT flags_json FROM edges").fetchall()
        for row in rows:
            flags = json.loads(row["flags_json"])
            assert flags["prior_only"] is False

    def test_audit_trail_written(self) -> None:
        """edge_updates table has one row per observation."""
        conn = _setup_minimal()
        apply_all_observations(conn)

        count = conn.execute("SELECT COUNT(*) FROM edge_updates").fetchone()[0]
        assert count == 3

    def test_audit_trail_content(self) -> None:
        """Audit trail records before/after state correctly."""
        conn = _setup_minimal()
        apply_all_observations(conn)

        rows = conn.execute(
            "SELECT * FROM edge_updates ORDER BY update_id"
        ).fetchall()

        # First observation
        assert rows[0]["alpha_before"] == 1
        assert rows[0]["alpha_after"] == 77
        assert rows[0]["polarity"] == "SUPPORT"
        assert rows[0]["increment"] == 76


class TestFrozenCollision:
    """Spec §9.4: Frozen edge collision rules."""

    def test_frozen_edge_records_obs_but_no_update(self) -> None:
        """Frozen edge: observation recorded, alpha/beta unchanged."""
        conn = _setup_minimal()

        # Freeze edge A→B first
        edge_ids = _get_edge_ids(conn)
        eid = edge_ids[0]
        conn.execute(
            "UPDATE edges SET frozen = 1, status = 'CONFIRMED', "
            "alpha_i = 9900, beta_i = 100 WHERE edge_id = ?",
            (eid,),
        )
        conn.commit()

        # Apply observations
        results = apply_all_observations(conn)

        # Find results for the frozen edge
        frozen_results = [r for r in results if r["frozen_before"] == 1]
        assert len(frozen_results) >= 1

        for r in frozen_results:
            assert r["alpha_before"] == r["alpha_after"]
            assert r["beta_before"] == r["beta_after"]

    def test_frozen_collision_sets_conflict_flag(self) -> None:
        """Contradictory DIRECT non-counterfactual on frozen REFUTED → conflict."""
        conn = _setup_minimal()

        edge_ids = _get_edge_ids(conn)
        eid = edge_ids[0]

        # Set frozen REFUTED
        conn.execute(
            "UPDATE edges SET frozen = 1, status = 'REFUTED', "
            "alpha_i = 100, beta_i = 9900 WHERE edge_id = ?",
            (eid,),
        )
        conn.commit()

        # Insert a contradictory ALLOW observation
        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant, evidence_hash)
               VALUES (?, 'REPLAY_SCRIPTED', 'ALLOW', 'UNKNOWN',
                       'DETERMINISTIC', 100, 0, 0, 'conflict_test')""",
            (eid,),
        )
        conn.commit()

        obs_id = conn.execute("SELECT MAX(observation_id) FROM observations").fetchone()[0]

        result = apply_observation(
            conn, obs_id, eid, "REPLAY_SCRIPTED", "ALLOW", "UNKNOWN",
            "DETERMINISTIC", 100, 0, 0, "conflict_test",
        )

        assert result["conflict_set"] is True

        e = _get_edge(conn, eid)
        flags = json.loads(e["flags_json"])
        assert flags["conflict"] is True

    def test_counterfactual_does_not_set_conflict(self) -> None:
        """Spec §9.4: Counterfactual on frozen edge does NOT set conflict."""
        conn = _setup_minimal()

        edge_ids = _get_edge_ids(conn)
        eid = edge_ids[0]

        conn.execute(
            "UPDATE edges SET frozen = 1, status = 'CONFIRMED', "
            "alpha_i = 9900, beta_i = 100 WHERE edge_id = ?",
            (eid,),
        )
        conn.commit()

        # Contradictory but counterfactual
        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant, evidence_hash)
               VALUES (?, 'WHATIF_FORCED', 'DENY', 'CONSTRAINT_DENY',
                       'DETERMINISTIC', 100, 1, 0, 'cf_test')""",
            (eid,),
        )
        conn.commit()

        obs_id = conn.execute("SELECT MAX(observation_id) FROM observations").fetchone()[0]

        result = apply_observation(
            conn, obs_id, eid, "WHATIF_FORCED", "DENY", "CONSTRAINT_DENY",
            "DETERMINISTIC", 100, 1, 0, "cf_test",
        )

        assert result["conflict_set"] is False

        e = _get_edge(conn, eid)
        flags = json.loads(e["flags_json"])
        assert flags["conflict"] is False


class TestDeterministicSaturation:
    """Spec §9.3: DETERMINISTIC observations saturate edges."""

    def test_deterministic_allow_saturates(self) -> None:
        conn = _setup_minimal()
        edge_ids = _get_edge_ids(conn)
        eid = edge_ids[0]

        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant, evidence_hash)
               VALUES (?, 'REPLAY_SCRIPTED', 'ALLOW', 'UNKNOWN',
                       'DETERMINISTIC', 100, 0, 0, 'det_allow')""",
            (eid,),
        )
        conn.commit()

        obs_id = conn.execute("SELECT MAX(observation_id) FROM observations").fetchone()[0]

        result = apply_observation(
            conn, obs_id, eid, "REPLAY_SCRIPTED", "ALLOW", "UNKNOWN",
            "DETERMINISTIC", 100, 0, 0, "det_allow",
        )

        assert result["alpha_after"] == 9900
        assert result["beta_after"] == 100
        assert result["status_after"] == "CONFIRMED"
        assert result["frozen_after"] == 1

    def test_deterministic_deny_saturates(self) -> None:
        conn = _setup_minimal()
        edge_ids = _get_edge_ids(conn)
        eid = edge_ids[0]

        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant, evidence_hash)
               VALUES (?, 'REPLAY_SCRIPTED', 'DENY', 'CONSTRAINT_DENY',
                       'DETERMINISTIC', 100, 0, 0, 'det_deny')""",
            (eid,),
        )
        conn.commit()

        obs_id = conn.execute("SELECT MAX(observation_id) FROM observations").fetchone()[0]

        result = apply_observation(
            conn, obs_id, eid, "REPLAY_SCRIPTED", "DENY", "CONSTRAINT_DENY",
            "DETERMINISTIC", 100, 0, 0, "det_deny",
        )

        assert result["alpha_after"] == 100
        assert result["beta_after"] == 9900
        assert result["status_after"] == "REFUTED"
        assert result["frozen_after"] == 1


class TestTemplateAggregation:
    """Spec §11: Template updates from observations."""

    def test_template_updated_for_eligible_obs(self) -> None:
        conn = _setup_minimal()
        results = apply_all_observations(conn)
        # Obs 1 (DIRECT, ALLOW, non-counterfactual) should update template
        assert results[0]["template_updated"] is True

    def test_template_not_updated_for_heuristic(self) -> None:
        """HEURISTIC does not update templates."""
        conn = _setup_minimal()
        edge_ids = _get_edge_ids(conn)
        eid = edge_ids[0]

        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant, evidence_hash)
               VALUES (?, 'REPLAY_SCRIPTED', 'ALLOW', 'UNKNOWN',
                       'HEURISTIC', 50, 0, 0, 'heur_test')""",
            (eid,),
        )
        conn.commit()

        obs_id = conn.execute("SELECT MAX(observation_id) FROM observations").fetchone()[0]

        result = apply_observation(
            conn, obs_id, eid, "REPLAY_SCRIPTED", "ALLOW", "UNKNOWN",
            "HEURISTIC", 50, 0, 0, "heur_test",
        )

        assert result["template_updated"] is False

    def test_template_not_updated_for_counterfactual(self) -> None:
        conn = _setup_minimal()
        edge_ids = _get_edge_ids(conn)
        eid = edge_ids[0]

        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant, evidence_hash)
               VALUES (?, 'WHATIF_FORCED', 'DENY', 'CONSTRAINT_DENY',
                       'DIRECT', 80, 1, 0, 'cf_tpl_test')""",
            (eid,),
        )
        conn.commit()

        obs_id = conn.execute("SELECT MAX(observation_id) FROM observations").fetchone()[0]

        result = apply_observation(
            conn, obs_id, eid, "WHATIF_FORCED", "DENY", "CONSTRAINT_DENY",
            "DIRECT", 80, 1, 0, "cf_tpl_test",
        )

        assert result["template_updated"] is False

    def test_template_alpha_increases_on_support(self) -> None:
        conn = _setup_minimal()

        # Get template state before
        tpl = conn.execute("SELECT alpha_agg_i, beta_agg_i FROM templates").fetchone()
        alpha_before = tpl["alpha_agg_i"]

        apply_all_observations(conn)

        tpl = conn.execute("SELECT alpha_agg_i, beta_agg_i, sample_count FROM templates").fetchone()
        # Two SUPPORT obs (obs 1 and 3) should increase alpha
        assert tpl["alpha_agg_i"] > alpha_before
        assert tpl["sample_count"] >= 2  # At least 2 eligible obs
