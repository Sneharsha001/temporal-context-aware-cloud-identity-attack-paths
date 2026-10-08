"""Tests for engine/correlation.py (spec §14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from arf_rt.adapters.replay import ReplayAdapter
from arf_rt.adapters.seed_json import load_scenario_file
from arf_rt.engine.correlation import (
    UnionFind,
    build_global_components,
    compute_correlation,
    compute_edge_groups,
    refresh_correlation_representatives,
    select_group_representatives,
    _rational_less,
)
from arf_rt.engine.updater import apply_all_observations
from arf_rt.storage.sqlite_store import connect
from arf_rt.util.canon import (
    canonical_json,
    features_fp as compute_features_fp,
    make_constraint_id,
    make_constraint_key,
    make_edge_id,
    make_flags_json,
    make_node_id,
    make_template_id,
    make_template_key,
    properties_fp as compute_properties_fp,
)


FIXTURES = Path(__file__).parent.parent / "fixtures"
MINIMAL = FIXTURES / "minimal_scenario.json"


def _full_pipeline():
    conn = connect(":memory:")
    scenario = load_scenario_file(MINIMAL)
    adapter = ReplayAdapter(conn)
    adapter.ingest(scenario)
    apply_all_observations(conn)
    conn.commit()
    return conn


# ===================================================================
# UnionFind
# ===================================================================


class TestUnionFind:
    def test_find_creates_singleton(self) -> None:
        uf = UnionFind()
        assert uf.find("a") == "a"

    def test_union_links(self) -> None:
        uf = UnionFind()
        uf.union("a", "b")
        assert uf.find("a") == uf.find("b")

    def test_three_way_union(self) -> None:
        uf = UnionFind()
        uf.union("a", "b")
        uf.union("b", "c")
        assert uf.find("a") == uf.find("c")

    def test_components(self) -> None:
        uf = UnionFind()
        uf.union("a", "b")
        uf.find("c")  # singleton
        comps = uf.components()
        assert len(comps) == 2
        # One component has {a,b}, another has {c}
        sizes = sorted(len(v) for v in comps.values())
        assert sizes == [1, 2]


# ===================================================================
# Rational compare (§14.5)
# ===================================================================


class TestRationalLess:
    def test_lower_ratio_is_less(self) -> None:
        # 1/10 < 9/10
        assert _rational_less(1, 9, 9, 1) is True

    def test_higher_ratio_is_not_less(self) -> None:
        assert _rational_less(9, 1, 1, 9) is False

    def test_equal_ratio_is_not_less(self) -> None:
        # 1/2 vs 2/4 → equal
        assert _rational_less(1, 1, 2, 2) is False

    def test_close_ratios(self) -> None:
        # 50/100 vs 51/100 — cross multiply: 50*151 vs 51*150
        # 7550 < 7650 → True
        assert _rational_less(50, 50, 51, 49) is True


# ===================================================================
# Global components (§14.2)
# ===================================================================


class TestGlobalComponents:
    def test_minimal_scenario_no_eligible_constraints(self) -> None:
        """Minimal scenario SCP has confidence_q=0 < threshold(500)."""
        conn = _full_pipeline()
        components = build_global_components(conn)
        # SCP confidence_q=0 < 500, so no eligible constraints
        assert len(components) == 0

    def test_with_high_confidence_constraint(self) -> None:
        """When confidence_q >= threshold, constraint appears in components."""
        conn = _full_pipeline()
        # Boost constraint confidence
        conn.execute("UPDATE constraints SET confidence_q = 800")
        conn.commit()

        components = build_global_components(conn)
        assert len(components) == 1  # One SCP constraint

    def test_component_id_is_min_constraint_id(self) -> None:
        """§14.3: component_id = min(constraint_id) in component."""
        conn = _full_pipeline()
        conn.execute("UPDATE constraints SET confidence_q = 800")
        conn.commit()

        components = build_global_components(conn)
        for cid, info in components.items():
            assert info["component_id"] <= cid  # component_id is min


# ===================================================================
# Edge groups (§14.4)
# ===================================================================


class TestEdgeGroups:
    def test_no_constraints_uses_edge_id(self) -> None:
        """Edges with no eligible constraints get ("NONE", edge_id) signature."""
        conn = _full_pipeline()
        # confidence_q=0 so no eligible constraints
        components = build_global_components(conn)
        groups = compute_edge_groups(conn, components)

        for eid, info in groups.items():
            expected = canonical_json([["NONE", eid]])
            assert info["p_worst_sig"] == expected
            assert info["p_best_sig"] == expected

    def test_with_constraints_grouped(self) -> None:
        """Edges sharing the same constraint get the same p_worst signature."""
        conn = _full_pipeline()
        conn.execute("UPDATE constraints SET confidence_q = 800")
        conn.commit()

        components = build_global_components(conn)
        groups = compute_edge_groups(conn, components)

        # Both edges linked to the same SCP should share p_worst signature
        sigs = set()
        for eid, info in groups.items():
            if info["constraint_ids"]:
                sigs.add(info["p_worst_sig"])

        # Both edges linked to same constraint → same component → same sig
        assert len(sigs) == 1

    def test_all_edges_have_groups(self) -> None:
        conn = _full_pipeline()
        components = build_global_components(conn)
        groups = compute_edge_groups(conn, components)
        edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        assert len(groups) == edge_count


# ===================================================================
# Representative selection (§14.5)
# ===================================================================


class TestRepresentativeSelection:
    def test_min_probability_selected(self) -> None:
        """Representative is the edge with lowest probability in group."""
        conn = _full_pipeline()
        conn.execute("UPDATE constraints SET confidence_q = 800")
        conn.commit()

        components = build_global_components(conn)
        groups = compute_edge_groups(conn, components)
        reps = select_group_representatives(conn, groups, "p_worst")

        # Check that each rep edge has the minimum ratio in its group
        edges = conn.execute("SELECT edge_id, alpha_i, beta_i FROM edges").fetchall()
        edge_beliefs = {r["edge_id"]: (r["alpha_i"], r["beta_i"]) for r in edges}

        for sig, rep_eid in reps.items():
            group_eids = [eid for eid, info in groups.items() if info["p_worst_sig"] == sig]
            rep_a, rep_b = edge_beliefs[rep_eid]
            for eid in group_eids:
                a, b = edge_beliefs[eid]
                # rep should be <= all others
                assert not _rational_less(a, b, rep_a, rep_b), \
                    f"Rep {rep_eid} is not minimum: {eid} has lower ratio"


# ===================================================================
# Full correlation pipeline
# ===================================================================


class TestFullCorrelation:
    def test_correlation_deterministic(self) -> None:
        """Same data → same correlation results."""
        c1 = compute_correlation(_full_pipeline())
        c2 = compute_correlation(_full_pipeline())
        # Compare component structure
        assert c1["components"] == c2["components"]
        # Compare group signatures
        for eid in c1["edge_groups"]:
            assert c1["edge_groups"][eid]["p_worst_sig"] == c2["edge_groups"][eid]["p_worst_sig"]
        assert c1["p_worst_reps"] == c2["p_worst_reps"]

    def test_correlation_active_only(self) -> None:
        """INVALIDATED constraints excluded from components."""
        conn = _full_pipeline()
        conn.execute("UPDATE constraints SET confidence_q = 800")
        conn.commit()

        c1 = compute_correlation(conn)
        assert len(c1["components"]) == 1

        # Invalidate the constraint
        conn.execute("UPDATE constraints SET status = 'INVALIDATED'")
        conn.commit()

        c2 = compute_correlation(conn)
        assert len(c2["components"]) == 0

    def test_refresh_representatives_reuses_static_membership(self) -> None:
        """Refreshing representatives matches full recompute after belief changes."""
        conn = _full_pipeline()
        conn.execute("UPDATE constraints SET confidence_q = 800")
        conn.commit()

        static = compute_correlation(conn)
        first_edge = conn.execute(
            "SELECT edge_id FROM edges ORDER BY edge_id COLLATE BINARY LIMIT 1"
        ).fetchone()["edge_id"]
        conn.execute(
            "UPDATE edges SET alpha_i = 1, beta_i = 99 WHERE edge_id = ?",
            (first_edge,),
        )
        conn.execute("UPDATE constraints SET validation_status = 'VALIDATED'")
        conn.commit()

        refreshed = refresh_correlation_representatives(conn, static)
        full = compute_correlation(conn)

        assert refreshed == full
