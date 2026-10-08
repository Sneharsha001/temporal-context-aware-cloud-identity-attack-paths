"""Golden determinism tests (spec §2.2, Session 4+7 integration gate).

THE critical test: same scenario → same canonical_run_hash.
If this fails, something in the deterministic pipeline is broken.

Session 7 upgrade: now includes full pipeline with correlation + paths.
"""

from __future__ import annotations

from pathlib import Path

from arf_rt.adapters.replay import ReplayAdapter
from arf_rt.adapters.seed_json import load_scenario_file
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.paths import search_and_store_top_k
from arf_rt.engine.snapshot import (
    canonical_run_hash,
    compute_all_obs_digests,
    full_state_export,
)
from arf_rt.engine.updater import apply_all_observations
from arf_rt.storage.sqlite_store import connect


FIXTURES = Path(__file__).parent.parent / "fixtures"
MINIMAL = FIXTURES / "minimal_scenario.json"


def _full_pipeline():
    """Complete pipeline: ingest → apply observations → return conn."""
    conn = connect(":memory:")
    scenario = load_scenario_file(MINIMAL)
    adapter = ReplayAdapter(conn)
    adapter.ingest(scenario)
    apply_all_observations(conn)
    conn.commit()
    return conn


def _full_pipeline_with_paths():
    """Complete pipeline including correlation + path search."""
    conn = _full_pipeline()
    corr = compute_correlation(conn)
    search_and_store_top_k(conn, corr)
    return conn


class TestReplayLogicalDeterminism:
    """THE golden test: same scenario, same hash, every time."""

    def test_replay_logical_determinism_hash_stable(self) -> None:
        """Run the full pipeline 5 times. All hashes must match."""
        hashes = []
        for _ in range(5):
            conn = _full_pipeline()
            h = canonical_run_hash(conn)
            hashes.append(h)
        assert len(set(hashes)) == 1, f"Hash instability: {hashes}"

    def test_full_pipeline_with_paths_hash_stable(self) -> None:
        """Full pipeline including paths: 5 runs, same hash."""
        hashes = []
        for _ in range(5):
            conn = _full_pipeline_with_paths()
            h = canonical_run_hash(conn)
            hashes.append(h)
        assert len(set(hashes)) == 1, f"Full pipeline hash instability: {hashes}"

    def test_obs_digests_stable_across_runs(self) -> None:
        digests_list = []
        for _ in range(3):
            conn = _full_pipeline()
            d = compute_all_obs_digests(conn)
            digests_list.append(d)
        for d in digests_list[1:]:
            assert d == digests_list[0]

    def test_edge_state_stable_across_runs(self) -> None:
        snapshots = []
        for _ in range(3):
            conn = _full_pipeline()
            rows = conn.execute(
                "SELECT edge_id, alpha_i, beta_i, status, frozen, flags_json "
                "FROM edges ORDER BY edge_id COLLATE BINARY"
            ).fetchall()
            snapshot = [
                (r["edge_id"], r["alpha_i"], r["beta_i"],
                 r["status"], r["frozen"], r["flags_json"])
                for r in rows
            ]
            snapshots.append(snapshot)
        for s in snapshots[1:]:
            assert s == snapshots[0]

    def test_template_state_stable_across_runs(self) -> None:
        snapshots = []
        for _ in range(3):
            conn = _full_pipeline()
            rows = conn.execute(
                "SELECT template_id, alpha_agg_i, beta_agg_i, sample_count "
                "FROM templates ORDER BY template_id COLLATE BINARY"
            ).fetchall()
            snapshot = [
                (r["template_id"], r["alpha_agg_i"], r["beta_agg_i"], r["sample_count"])
                for r in rows
            ]
            snapshots.append(snapshot)
        for s in snapshots[1:]:
            assert s == snapshots[0]

    def test_derived_topk_stable_across_runs(self) -> None:
        """Path search results are deterministic."""
        snapshots = []
        for _ in range(3):
            conn = _full_pipeline_with_paths()
            rows = conn.execute(
                "SELECT objective_id, rank, edge_id_sequence, p_worst_q8, p_best_q8 "
                "FROM derived_topk ORDER BY objective_id, rank"
            ).fetchall()
            snapshot = [(r["objective_id"], r["rank"], r["edge_id_sequence"],
                         r["p_worst_q8"], r["p_best_q8"]) for r in rows]
            snapshots.append(snapshot)
        for s in snapshots[1:]:
            assert s == snapshots[0]

    def test_full_state_export_stable(self) -> None:
        """full_state_export produces identical output across runs."""
        exports = []
        for _ in range(3):
            conn = _full_pipeline_with_paths()
            e = full_state_export(conn)
            exports.append(e["canonical_run_hash"])
        assert len(set(exports)) == 1
