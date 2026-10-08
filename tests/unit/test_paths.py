"""Tests for engine/paths.py (spec §15)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arf_rt.adapters.replay import ReplayAdapter
from arf_rt.adapters.seed_json import load_scenario_file
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.paths import search_and_store_top_k, search_top_k
from arf_rt.engine.updater import apply_all_observations
from arf_rt.storage.sqlite_store import connect
from arf_rt.util.canon import (
    canonical_json,
    features_fp as compute_features_fp,
    make_edge_id,
    make_flags_json,
    make_node_id,
    make_objective_id,
    make_template_id,
    make_template_key,
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


def _get_objective_id(conn):
    return conn.execute("SELECT objective_id FROM objectives").fetchone()["objective_id"]


# ===================================================================
# Basic path search
# ===================================================================


class TestSearchTopK:
    def test_finds_path_in_minimal_scenario(self) -> None:
        """Minimal scenario: A→B→C should be found."""
        conn = _full_pipeline()
        oid = _get_objective_id(conn)
        paths = search_top_k(conn, oid)
        assert len(paths) >= 1

    def test_path_has_two_edges(self) -> None:
        """A→B→C is a 2-edge path."""
        conn = _full_pipeline()
        oid = _get_objective_id(conn)
        paths = search_top_k(conn, oid)
        assert paths[0]["path_length"] == 2

    def test_path_edge_sequence_is_json_list(self) -> None:
        conn = _full_pipeline()
        oid = _get_objective_id(conn)
        paths = search_top_k(conn, oid)
        seq = json.loads(paths[0]["edge_id_sequence"])
        assert isinstance(seq, list)
        assert len(seq) == 2

    def test_path_has_confidence_band(self) -> None:
        conn = _full_pipeline()
        oid = _get_objective_id(conn)
        paths = search_top_k(conn, oid)
        assert paths[0]["confidence_band"] in (
            "VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW", "INSUFFICIENT"
        )

    def test_path_p_worst_and_p_best(self) -> None:
        conn = _full_pipeline()
        oid = _get_objective_id(conn)
        paths = search_top_k(conn, oid)
        # p_worst should be > 0 (there's a real path)
        assert paths[0]["p_worst_q8"] > 0
        assert paths[0]["p_best_q8"] > 0

    def test_ranks_sequential(self) -> None:
        conn = _full_pipeline()
        oid = _get_objective_id(conn)
        paths = search_top_k(conn, oid)
        for i, p in enumerate(paths):
            assert p["rank"] == i + 1

    def test_flags_json_valid(self) -> None:
        conn = _full_pipeline()
        oid = _get_objective_id(conn)
        paths = search_top_k(conn, oid)
        flags = json.loads(paths[0]["flags_json"])
        assert "conflict" in flags
        assert "prior_only" in flags


# ===================================================================
# Determinism
# ===================================================================


class TestPathDeterminism:
    def test_topk_deterministic_ordering(self) -> None:
        """Same data → same path order."""
        results = []
        for _ in range(3):
            conn = _full_pipeline()
            oid = _get_objective_id(conn)
            paths = search_top_k(conn, oid)
            results.append(
                [(p["edge_id_sequence"], p["p_worst_q8"]) for p in paths]
            )
        for r in results[1:]:
            assert r == results[0]


# ===================================================================
# Cycle safety
# ===================================================================


class TestCycleSafety:
    def test_cycle_safety_visited_nodes(self) -> None:
        """Paths don't revisit nodes."""
        conn = _full_pipeline()
        oid = _get_objective_id(conn)
        paths = search_top_k(conn, oid)

        for p in paths:
            seq = json.loads(p["edge_id_sequence"])
            # Get nodes along path
            nodes = set()
            for eid in seq:
                e = conn.execute(
                    "SELECT src_node_id, dst_node_id FROM edges WHERE edge_id = ?",
                    (eid,),
                ).fetchone()
                # Each dst should not have been a src before (no cycles)
                nodes.add(e["src_node_id"])
                nodes.add(e["dst_node_id"])
            # Number of unique nodes = path_length + 1 (no revisits)
            assert len(nodes) == p["path_length"] + 1


class TestMaxDepth:
    def test_max_depth_respected(self) -> None:
        """No path exceeds max_depth."""
        conn = _full_pipeline()
        oid = _get_objective_id(conn)

        obj = conn.execute(
            "SELECT max_depth FROM objectives WHERE objective_id = ?", (oid,)
        ).fetchone()
        max_depth = obj["max_depth"]

        paths = search_top_k(conn, oid)
        for p in paths:
            assert p["path_length"] <= max_depth


# ===================================================================
# Store results
# ===================================================================


class TestSearchAndStore:
    def test_stores_in_derived_topk(self) -> None:
        conn = _full_pipeline()
        search_and_store_top_k(conn)

        rows = conn.execute("SELECT * FROM derived_topk").fetchall()
        assert len(rows) >= 1

    def test_stored_values_match_search(self) -> None:
        conn = _full_pipeline()
        oid = _get_objective_id(conn)
        correlation = compute_correlation(conn)

        paths = search_top_k(conn, oid, correlation)
        search_and_store_top_k(conn, correlation)

        rows = conn.execute(
            "SELECT rank, edge_id_sequence, p_worst_q8, p_best_q8 "
            "FROM derived_topk WHERE objective_id = ? ORDER BY rank",
            (oid,),
        ).fetchall()

        assert len(rows) == len(paths)
        for row, path in zip(rows, paths):
            assert row["rank"] == path["rank"]
            assert row["edge_id_sequence"] == path["edge_id_sequence"]
            assert row["p_worst_q8"] == path["p_worst_q8"]

    def test_store_deterministic(self) -> None:
        """Stored results are the same across runs."""
        def _run():
            conn = _full_pipeline()
            search_and_store_top_k(conn)
            rows = conn.execute(
                "SELECT objective_id, rank, edge_id_sequence, p_worst_q8, p_best_q8 "
                "FROM derived_topk ORDER BY objective_id, rank"
            ).fetchall()
            return [(r["objective_id"], r["rank"], r["edge_id_sequence"],
                     r["p_worst_q8"], r["p_best_q8"]) for r in rows]

        r1 = _run()
        r2 = _run()
        assert r1 == r2


# ===================================================================
# No-path scenario
# ===================================================================


class TestNoPath:
    def test_unreachable_target_returns_empty(self) -> None:
        """If no path exists, returns empty list."""
        conn = _full_pipeline()

        # Add a disconnected node and objective to it
        nid = make_node_id("aws", "IAMRole", "isolated", "us-east-1")
        conn.execute(
            "INSERT INTO nodes (node_id, provider, node_type, provider_id, region, "
            "display_name, properties_json) VALUES (?, 'aws', 'IAMRole', 'isolated', "
            "'us-east-1', 'Isolated', '{}')",
            (nid,),
        )

        start_nid = conn.execute(
            "SELECT node_id FROM nodes WHERE provider_id = 'role-alpha'"
        ).fetchone()["node_id"]

        oid = make_objective_id("REACHABILITY", [start_nid], [nid], 5, 3)
        start_json = canonical_json(sorted([start_nid]))
        target_json = canonical_json(sorted([nid]))
        conn.execute(
            "INSERT INTO objectives (objective_id, objective_type, start_nodes_json, "
            "target_nodes_json, max_depth, k) VALUES (?, 'REACHABILITY', ?, ?, 5, 3)",
            (oid, start_json, target_json),
        )
        conn.commit()

        paths = search_top_k(conn, oid)
        assert paths == []
