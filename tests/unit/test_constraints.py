"""Tests for engine/constraints.py (spec §13)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arf_rt.adapters.replay import ReplayAdapter
from arf_rt.adapters.seed_json import load_scenario_file
from arf_rt.engine.constraints import (
    get_active_validated_constraints,
    invalidate_constraint,
    validate_all_constraints,
)
from arf_rt.engine.updater import apply_all_observations
from arf_rt.storage.sqlite_store import connect
from arf_rt.util.canon import (
    canonical_json,
    features_fp as compute_features_fp,
    make_constraint_id,
    make_edge_id,
    make_flags_json,
    make_node_id,
    make_template_id,
    make_template_key,
    properties_fp as compute_properties_fp,
)


FIXTURES = Path(__file__).parent.parent / "fixtures"
MINIMAL = FIXTURES / "minimal_scenario.json"


def _ingest_minimal():
    conn = connect(":memory:")
    scenario = load_scenario_file(MINIMAL)
    adapter = ReplayAdapter(conn)
    adapter.ingest(scenario)
    apply_all_observations(conn)
    conn.commit()
    return conn


def _build_rich_constraint_db():
    """Build a DB with an SCP constraint linked to 2 edges from 2 different sources.

    Setup:
      - 3 nodes: X, Y, Z
      - 2 edges: X→Z, Y→Z (different src_node_ids)
      - 1 SCP constraint linked to both edges
      - Qualifying observations on both edges (CONSTRAINT_DENY, DIRECT)
    """
    conn = connect(":memory:")

    # Nodes
    nids = {}
    for pid in ("x", "y", "z"):
        nid = make_node_id("aws", "IAMRole", pid, "us-east-1")
        nids[pid] = nid
        conn.execute(
            "INSERT INTO nodes (node_id, provider, node_type, provider_id, region, display_name, properties_json) "
            "VALUES (?, 'aws', 'IAMRole', ?, 'us-east-1', ?, '{}')",
            (nid, pid, pid.upper()),
        )

    # Template
    feat = {"action": "sts:AssumeRole"}
    feat_fp = compute_features_fp(feat)
    tpl_id = make_template_id("aws", "sts:AssumeRole", feat_fp, 1)
    tpl_key = make_template_key("aws", "sts:AssumeRole", feat_fp)
    conn.execute(
        "INSERT INTO templates (template_id, template_key, provider, edge_type, "
        "features_json, features_fp, feature_schema_version, alpha_agg_i, beta_agg_i, sample_count) "
        "VALUES (?, ?, 'aws', 'sts:AssumeRole', ?, ?, 1, 1, 1, 0)",
        (tpl_id, tpl_key, canonical_json(feat), feat_fp),
    )

    # Edges: X→Z and Y→Z
    edge_ids = {}
    for src in ("x", "y"):
        eid = make_edge_id("sts:AssumeRole", nids[src], nids["z"], "us-east-1", tpl_id)
        edge_ids[src] = eid
        conn.execute(
            "INSERT INTO edges (edge_id, edge_type, src_node_id, dst_node_id, region, "
            "template_id, alpha_i, beta_i, status, frozen, flags_json, features_json, features_fp) "
            "VALUES (?, 'sts:AssumeRole', ?, ?, 'us-east-1', ?, 1, 1, 'HYPOTHESIZED', 0, ?, ?, ?)",
            (eid, nids[src], nids["z"], tpl_id, make_flags_json(), canonical_json(feat), feat_fp),
        )

    # Constraint (SCP)
    cst_props = {"effect": "Deny", "action": "sts:AssumeRole"}
    cst_prop_fp = compute_properties_fp(cst_props)
    cst_id = make_constraint_id("aws", "SCP", "OU", "ou-001", "us-east-1", cst_prop_fp)
    from arf_rt.util.canon import make_constraint_key
    cst_key = make_constraint_key("aws", "SCP", "OU", "ou-001", "us-east-1", cst_prop_fp)
    conn.execute(
        "INSERT INTO constraints (constraint_id, constraint_key, provider, constraint_type, "
        "scope_type, scope_id, region, properties_json, properties_fp, status, validation_status, confidence_q) "
        "VALUES (?, ?, 'aws', 'SCP', 'OU', 'ou-001', 'us-east-1', ?, ?, 'ACTIVE', 'UNVALIDATED', 0)",
        (cst_id, cst_key, canonical_json(cst_props), cst_prop_fp),
    )

    # Link both edges to the constraint
    for src in ("x", "y"):
        conn.execute(
            "INSERT INTO edge_constraints (edge_id, constraint_id, relation_type) VALUES (?, ?, 'APPLIES_TO')",
            (edge_ids[src], cst_id),
        )

    conn.commit()
    return conn, edge_ids, cst_id, nids


def _add_qualifying_obs(conn, edge_id, reason_class="CONSTRAINT_DENY", constraint_relevant=1):
    """Add a qualifying observation (non-counterfactual, DIRECT, constraint-relevant)."""
    conn.execute(
        """INSERT INTO observations
           (edge_id, probe_type, result, reason_class, strength,
            signal_q, is_counterfactual, constraint_relevant, evidence_hash)
           VALUES (?, 'REPLAY_SCRIPTED', 'DENY', ?, 'DIRECT', 80, 0, ?, 'ev_hash')""",
        (edge_id, reason_class, constraint_relevant),
    )
    conn.commit()


# ===================================================================
# Relevance rule tests (§13.1)
# ===================================================================


class TestRelevanceRule:
    """SCP/PERMISSION_BOUNDARY only count constraint-relevant observations."""

    def test_constraint_deny_qualifies(self) -> None:
        """reason_class=CONSTRAINT_DENY qualifies under relevance rule."""
        conn, edge_ids, cst_id, _ = _build_rich_constraint_db()
        _add_qualifying_obs(conn, edge_ids["x"], reason_class="CONSTRAINT_DENY", constraint_relevant=0)
        _add_qualifying_obs(conn, edge_ids["y"], reason_class="CONSTRAINT_DENY", constraint_relevant=0)

        results = validate_all_constraints(conn)
        r = results[0]
        assert r["new_status"] == "VALIDATED"
        assert r["distinct_edges"] == 2
        assert r["distinct_sources"] == 2

    def test_constraint_relevant_flag_qualifies(self) -> None:
        """constraint_relevant=1 qualifies even without CONSTRAINT_DENY."""
        conn, edge_ids, cst_id, _ = _build_rich_constraint_db()
        _add_qualifying_obs(conn, edge_ids["x"], reason_class="MISSING_PERMISSION", constraint_relevant=1)
        _add_qualifying_obs(conn, edge_ids["y"], reason_class="MISSING_PERMISSION", constraint_relevant=1)

        results = validate_all_constraints(conn)
        assert results[0]["new_status"] == "VALIDATED"

    def test_non_relevant_obs_excluded(self) -> None:
        """Obs with reason_class≠CONSTRAINT_DENY AND constraint_relevant=0 excluded."""
        conn, edge_ids, cst_id, _ = _build_rich_constraint_db()
        # Add non-qualifying observations (MISSING_PERMISSION + not constraint_relevant)
        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant, evidence_hash)
               VALUES (?, 'REPLAY_SCRIPTED', 'DENY', 'MISSING_PERMISSION', 'DIRECT', 80, 0, 0, 'ev1')""",
            (edge_ids["x"],),
        )
        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant, evidence_hash)
               VALUES (?, 'REPLAY_SCRIPTED', 'DENY', 'MISSING_PERMISSION', 'DIRECT', 80, 0, 0, 'ev2')""",
            (edge_ids["y"],),
        )
        conn.commit()

        results = validate_all_constraints(conn)
        assert results[0]["new_status"] == "UNVALIDATED"
        assert results[0]["distinct_edges"] == 0

    def test_counterfactual_excluded(self) -> None:
        """Counterfactual observations excluded."""
        conn, edge_ids, cst_id, _ = _build_rich_constraint_db()
        # Add counterfactual observations
        for src in ("x", "y"):
            conn.execute(
                """INSERT INTO observations
                   (edge_id, probe_type, result, reason_class, strength,
                    signal_q, is_counterfactual, constraint_relevant, evidence_hash)
                   VALUES (?, 'WHATIF_FORCED', 'DENY', 'CONSTRAINT_DENY', 'DIRECT', 80, 1, 1, 'cf')""",
                (edge_ids[src],),
            )
        conn.commit()

        results = validate_all_constraints(conn)
        assert results[0]["new_status"] == "UNVALIDATED"

    def test_inferred_excluded(self) -> None:
        """INFERRED strength excluded (needs DIRECT or DETERMINISTIC)."""
        conn, edge_ids, cst_id, _ = _build_rich_constraint_db()
        for src in ("x", "y"):
            conn.execute(
                """INSERT INTO observations
                   (edge_id, probe_type, result, reason_class, strength,
                    signal_q, is_counterfactual, constraint_relevant, evidence_hash)
                   VALUES (?, 'REPLAY_SCRIPTED', 'DENY', 'CONSTRAINT_DENY', 'INFERRED', 80, 0, 1, 'inf')""",
                (edge_ids[src],),
            )
        conn.commit()

        results = validate_all_constraints(conn)
        assert results[0]["new_status"] == "UNVALIDATED"


# ===================================================================
# Threshold tests (§13.2)
# ===================================================================


class TestSCPThresholds:
    """SCP requires ≥N distinct edges spanning ≥M distinct src_node_ids."""

    def test_scp_requires_n_edges_m_sources(self) -> None:
        """Both thresholds must be met."""
        conn, edge_ids, cst_id, _ = _build_rich_constraint_db()
        _add_qualifying_obs(conn, edge_ids["x"])
        _add_qualifying_obs(conn, edge_ids["y"])

        results = validate_all_constraints(conn, n=2, m=2)
        assert results[0]["new_status"] == "VALIDATED"

    def test_scp_insufficient_edges(self) -> None:
        """Only 1 qualifying edge when N=2 → UNVALIDATED."""
        conn, edge_ids, cst_id, _ = _build_rich_constraint_db()
        _add_qualifying_obs(conn, edge_ids["x"])
        # Only one edge has qualifying obs

        results = validate_all_constraints(conn, n=2, m=2)
        assert results[0]["new_status"] == "UNVALIDATED"
        assert results[0]["distinct_edges"] == 1

    def test_scp_insufficient_sources(self) -> None:
        """2 edges but same src → only 1 distinct source when M=2 → UNVALIDATED.

        We build a custom scenario where both edges share the same src_node_id.
        """
        conn = connect(":memory:")

        # 2 nodes: X, Z
        nid_x = make_node_id("aws", "IAMRole", "x", "us-east-1")
        nid_z = make_node_id("aws", "IAMRole", "z", "us-east-1")
        nid_z2 = make_node_id("aws", "IAMRole", "z2", "us-east-1")
        for nid, pid in [(nid_x, "x"), (nid_z, "z"), (nid_z2, "z2")]:
            conn.execute(
                "INSERT INTO nodes (node_id, provider, node_type, provider_id, region, display_name, properties_json) "
                "VALUES (?, 'aws', 'IAMRole', ?, 'us-east-1', ?, '{}')",
                (nid, pid, pid.upper()),
            )

        feat = {"action": "test"}
        feat_fp = compute_features_fp(feat)
        tpl_id = make_template_id("aws", "test", feat_fp, 1)
        tpl_key = make_template_key("aws", "test", feat_fp)
        conn.execute(
            "INSERT INTO templates (template_id, template_key, provider, edge_type, "
            "features_json, features_fp, feature_schema_version, alpha_agg_i, beta_agg_i, sample_count) "
            "VALUES (?, ?, 'aws', 'test', ?, ?, 1, 1, 1, 0)",
            (tpl_id, tpl_key, canonical_json(feat), feat_fp),
        )

        # 2 edges: X→Z and X→Z2 (same src X)
        eid1 = make_edge_id("test", nid_x, nid_z, "us-east-1", tpl_id)
        eid2 = make_edge_id("test", nid_x, nid_z2, "us-east-1", tpl_id)
        for eid, dst in [(eid1, nid_z), (eid2, nid_z2)]:
            conn.execute(
                "INSERT INTO edges (edge_id, edge_type, src_node_id, dst_node_id, region, "
                "template_id, alpha_i, beta_i, status, frozen, flags_json, features_json, features_fp) "
                "VALUES (?, 'test', ?, ?, 'us-east-1', ?, 1, 1, 'HYPOTHESIZED', 0, ?, ?, ?)",
                (eid, nid_x, dst, tpl_id, make_flags_json(), canonical_json(feat), feat_fp),
            )

        # SCP constraint
        cst_props = {"effect": "Deny"}
        cst_prop_fp = compute_properties_fp(cst_props)
        cst_id = make_constraint_id("aws", "SCP", "OU", "ou", "us-east-1", cst_prop_fp)
        from arf_rt.util.canon import make_constraint_key
        cst_key = make_constraint_key("aws", "SCP", "OU", "ou", "us-east-1", cst_prop_fp)
        conn.execute(
            "INSERT INTO constraints (constraint_id, constraint_key, provider, constraint_type, "
            "scope_type, scope_id, region, properties_json, properties_fp, status, validation_status, confidence_q) "
            "VALUES (?, ?, 'aws', 'SCP', 'OU', 'ou', 'us-east-1', ?, ?, 'ACTIVE', 'UNVALIDATED', 0)",
            (cst_id, cst_key, canonical_json(cst_props), cst_prop_fp),
        )
        conn.execute("INSERT INTO edge_constraints VALUES (?, ?, 'APPLIES_TO', datetime('now'))", (eid1, cst_id))
        conn.execute("INSERT INTO edge_constraints VALUES (?, ?, 'APPLIES_TO', datetime('now'))", (eid2, cst_id))
        conn.commit()

        # Add qualifying obs on both edges
        _add_qualifying_obs(conn, eid1)
        _add_qualifying_obs(conn, eid2)

        results = validate_all_constraints(conn, n=2, m=2)
        # 2 edges but only 1 distinct source (X)
        assert results[0]["distinct_edges"] == 2
        assert results[0]["distinct_sources"] == 1
        assert results[0]["new_status"] == "UNVALIDATED"


class TestTrustConditionThreshold:
    """TRUST_CONDITION requires ≥1 qualifying observation."""

    def test_trust_condition_requires_one_observation(self) -> None:
        conn, edge_ids, _, _ = _build_rich_constraint_db()

        # Change constraint type to TRUST_CONDITION
        conn.execute("UPDATE constraints SET constraint_type = 'TRUST_CONDITION'")
        conn.commit()

        # No observations yet
        results = validate_all_constraints(conn)
        assert results[0]["new_status"] == "UNVALIDATED"

        # Add one qualifying observation
        _add_qualifying_obs(conn, edge_ids["x"], reason_class="UNKNOWN", constraint_relevant=0)

        results = validate_all_constraints(conn)
        assert results[0]["new_status"] == "VALIDATED"

    def test_trust_condition_no_relevance_filter(self) -> None:
        """TRUST_CONDITION doesn't require CONSTRAINT_DENY or constraint_relevant."""
        conn, edge_ids, _, _ = _build_rich_constraint_db()
        conn.execute("UPDATE constraints SET constraint_type = 'TRUST_CONDITION'")
        conn.commit()

        # Add obs with reason_class=UNKNOWN and constraint_relevant=0
        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant, evidence_hash)
               VALUES (?, 'REPLAY_SCRIPTED', 'ALLOW', 'UNKNOWN', 'DIRECT', 80, 0, 0, 'ev')""",
            (edge_ids["x"],),
        )
        conn.commit()

        results = validate_all_constraints(conn)
        assert results[0]["new_status"] == "VALIDATED"


# ===================================================================
# ASSUMED status (§13.3)
# ===================================================================


class TestAssumedStatus:
    """ASSUMED counts as unvalidated."""

    def test_assumed_counts_as_unvalidated(self) -> None:
        conn, edge_ids, cst_id, _ = _build_rich_constraint_db()
        conn.execute(
            "UPDATE constraints SET validation_status = 'ASSUMED' WHERE constraint_id = ?",
            (cst_id,),
        )
        conn.commit()

        # No qualifying observations → should go to UNVALIDATED
        results = validate_all_constraints(conn)
        assert results[0]["old_status"] == "ASSUMED"
        assert results[0]["new_status"] == "UNVALIDATED"

    def test_assumed_not_in_active_validated(self) -> None:
        """ASSUMED constraints not returned by get_active_validated_constraints."""
        conn, _, cst_id, _ = _build_rich_constraint_db()
        conn.execute(
            "UPDATE constraints SET validation_status = 'ASSUMED' WHERE constraint_id = ?",
            (cst_id,),
        )
        conn.commit()

        validated = get_active_validated_constraints(conn)
        cst_ids = {c["constraint_id"] for c in validated}
        assert cst_id not in cst_ids


# ===================================================================
# Invalidation propagation (§13.4)
# ===================================================================


class TestInvalidation:
    """INVALIDATED constraints excluded from everything."""

    def test_invalidated_constraint_excluded_from_validation(self) -> None:
        conn, edge_ids, cst_id, _ = _build_rich_constraint_db()
        invalidate_constraint(conn, cst_id)
        conn.commit()

        # Validate — should return empty since only constraint is INVALIDATED
        results = validate_all_constraints(conn)
        assert len(results) == 0  # INVALIDATED is not ACTIVE

    def test_invalidated_not_in_active_validated(self) -> None:
        conn, _, cst_id, _ = _build_rich_constraint_db()
        _add_qualifying_obs(conn, list(conn.execute(
            "SELECT edge_id FROM edge_constraints WHERE constraint_id = ?", (cst_id,)
        ).fetchall())[0]["edge_id"])

        # First validate it
        validate_all_constraints(conn)
        conn.commit()

        # Then invalidate
        invalidate_constraint(conn, cst_id)
        conn.commit()

        validated = get_active_validated_constraints(conn)
        assert len(validated) == 0

    def test_invalidate_updates_status(self) -> None:
        conn, _, cst_id, _ = _build_rich_constraint_db()
        invalidate_constraint(conn, cst_id)
        conn.commit()

        row = conn.execute(
            "SELECT status FROM constraints WHERE constraint_id = ?", (cst_id,)
        ).fetchone()
        assert row["status"] == "INVALIDATED"


# ===================================================================
# Minimal scenario integration
# ===================================================================


class TestMinimalScenarioConstraints:
    """Constraint validation with the golden minimal scenario."""

    def test_minimal_scenario_scp_unvalidated(self) -> None:
        """In minimal scenario, SCP has only 1 qualifying edge (B→C with CONSTRAINT_DENY).
        Edge A→B obs are ALLOW/UNKNOWN which don't pass relevance rule.
        So SCP stays UNVALIDATED (needs ≥2 edges, ≥2 sources).
        """
        conn = _ingest_minimal()
        results = validate_all_constraints(conn)
        assert len(results) == 1
        assert results[0]["constraint_type"] == "SCP"
        assert results[0]["new_status"] == "UNVALIDATED"
        # Only edge B→C qualifies (DENY + CONSTRAINT_DENY)
        assert results[0]["distinct_edges"] == 1

    def test_validation_deterministic(self) -> None:
        """Same scenario → same validation results."""
        r1 = validate_all_constraints(_ingest_minimal())
        r2 = validate_all_constraints(_ingest_minimal())
        assert r1 == r2
