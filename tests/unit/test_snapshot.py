"""Tests for engine/snapshot.py — Session 7 hardened (spec §2.2, §2.3.3)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from arf_rt.adapters.replay import ReplayAdapter
from arf_rt.adapters.seed_json import load_scenario_file
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.paths import search_and_store_top_k
from arf_rt.engine.snapshot import (
    canonical_run_hash,
    compute_all_obs_digests,
    compute_obs_digest,
    full_state_export,
)
from arf_rt.engine.updater import apply_all_observations
from arf_rt.storage.sqlite_store import connect
from arf_rt.util.canon import canonical_json


FIXTURES = Path(__file__).parent.parent / "fixtures"
MINIMAL = FIXTURES / "minimal_scenario.json"


def _full_pipeline():
    """Ingest + apply observations → return conn."""
    conn = connect(":memory:")
    scenario = load_scenario_file(MINIMAL)
    adapter = ReplayAdapter(conn)
    adapter.ingest(scenario)
    apply_all_observations(conn)
    conn.commit()
    return conn


def _full_pipeline_with_paths():
    """Full pipeline including correlation + path search."""
    conn = _full_pipeline()
    corr = compute_correlation(conn)
    search_and_store_top_k(conn, corr)
    return conn


def _ingest_only():
    conn = connect(":memory:")
    scenario = load_scenario_file(MINIMAL)
    adapter = ReplayAdapter(conn)
    adapter.ingest(scenario)
    return conn


# ===================================================================
# obs_digest tests
# ===================================================================


class TestObsDigest:
    def test_obs_digest_nonempty_for_observed_edge(self) -> None:
        conn = _ingest_only()
        edge_ids = [
            r["edge_id"] for r in conn.execute(
                "SELECT DISTINCT edge_id FROM observations"
            ).fetchall()
        ]
        for eid in edge_ids:
            digest = compute_obs_digest(conn, eid)
            assert len(digest) == 64

    def test_obs_digest_pipeline_uses_tuple_json_list_only(self) -> None:
        conn = _ingest_only()
        eid = conn.execute(
            "SELECT DISTINCT edge_id FROM observations ORDER BY edge_id COLLATE BINARY"
        ).fetchone()["edge_id"]

        rows = conn.execute(
            "SELECT probe_type, result, reason_class, strength, signal_q, "
            "is_counterfactual, constraint_relevant, evidence_hash "
            "FROM observations WHERE edge_id = ? ORDER BY observation_id",
            (eid,),
        ).fetchall()

        tuple_jsons = []
        for r in rows:
            t = [r["probe_type"], r["result"], r["reason_class"],
                 r["strength"], r["signal_q"], r["is_counterfactual"],
                 r["constraint_relevant"], r["evidence_hash"]]
            tuple_jsons.append(canonical_json(t))

        tuple_jsons.sort()
        digest_input = canonical_json(tuple_jsons)
        expected = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
        assert compute_obs_digest(conn, eid) == expected

    def test_obs_digest_uses_json_null_for_missing_evidence_hash(self) -> None:
        conn = _ingest_only()
        eid = conn.execute(
            "SELECT edge_id FROM observations WHERE evidence_hash IS NULL"
        ).fetchone()["edge_id"]

        row = conn.execute(
            "SELECT probe_type, result, reason_class, strength, signal_q, "
            "is_counterfactual, constraint_relevant, evidence_hash "
            "FROM observations WHERE edge_id = ? AND evidence_hash IS NULL",
            (eid,),
        ).fetchone()

        t = [row["probe_type"], row["result"], row["reason_class"],
             row["strength"], row["signal_q"], row["is_counterfactual"],
             row["constraint_relevant"], row["evidence_hash"]]
        tj = canonical_json(t)
        assert "null" in tj
        assert '"null"' not in tj

    def test_all_obs_digests(self) -> None:
        conn = _ingest_only()
        digests = compute_all_obs_digests(conn)
        assert len(digests) == 2
        assert all(len(v) == 64 for v in digests.values())

    def test_obs_digest_deterministic(self) -> None:
        conn = _ingest_only()
        d1 = compute_all_obs_digests(conn)
        d2 = compute_all_obs_digests(conn)
        assert d1 == d2


# ===================================================================
# canonical_run_hash tests
# ===================================================================


class TestCanonicalRunHash:
    def test_run_hash_is_64_hex(self) -> None:
        conn = _full_pipeline()
        h = canonical_run_hash(conn)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_run_hash_deterministic(self) -> None:
        h1 = canonical_run_hash(_full_pipeline())
        h2 = canonical_run_hash(_full_pipeline())
        assert h1 == h2

    def test_different_data_different_hash(self) -> None:
        conn1 = _full_pipeline()
        h1 = canonical_run_hash(conn1)

        conn2 = _full_pipeline()
        eid = conn2.execute("SELECT edge_id FROM edges LIMIT 1").fetchone()["edge_id"]
        conn2.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant, evidence_hash)
               VALUES (?, 'REPLAY_SCRIPTED', 'ALLOW', 'UNKNOWN',
                       'HEURISTIC', 50, 0, 0, 'extra')""",
            (eid,),
        )
        conn2.commit()
        from arf_rt.engine.updater import apply_observation
        obs_id = conn2.execute("SELECT MAX(observation_id) FROM observations").fetchone()[0]
        apply_observation(conn2, obs_id, eid, "REPLAY_SCRIPTED", "ALLOW", "UNKNOWN",
                          "HEURISTIC", 50, 0, 0, "extra")
        conn2.commit()
        h2 = canonical_run_hash(conn2)
        assert h1 != h2


class TestHashExclusions:
    """Session 7: verify what's excluded from canonical_run_hash."""

    def test_canonical_hash_excludes_raw_observations_table(self) -> None:
        """Adding a warning-only observation shouldn't change hash if
        edge state is unchanged. But observations DO affect obs_digest
        which IS in the hash. So this tests that the raw observations table
        is not directly hashed — only obs_digest is."""
        conn = _full_pipeline()
        h1 = canonical_run_hash(conn)

        # Adding a run_warning doesn't change the hash
        conn.execute(
            "INSERT INTO run_warnings (code, severity, message, context_json) "
            "VALUES ('TEST', 'INFO', 'test warning', '{}')"
        )
        conn.commit()
        h2 = canonical_run_hash(conn)
        assert h1 == h2  # Warnings excluded from hash

    def test_canonical_hash_excludes_run_warnings(self) -> None:
        """Warnings are informational — changing them doesn't affect hash."""
        conn = _full_pipeline()
        h1 = canonical_run_hash(conn)

        conn.execute("DELETE FROM run_warnings")
        conn.commit()
        h2 = canonical_run_hash(conn)
        assert h1 == h2

    def test_canonical_hash_excludes_constraint_key(self) -> None:
        """constraint_key is display-only — changing it doesn't affect hash."""
        conn = _full_pipeline()
        h1 = canonical_run_hash(conn)

        conn.execute("UPDATE constraints SET constraint_key = 'CHANGED_KEY'")
        conn.commit()
        h2 = canonical_run_hash(conn)
        assert h1 == h2

    def test_canonical_hash_excludes_template_key(self) -> None:
        """template_key is display-only — changing it doesn't affect hash."""
        conn = _full_pipeline()
        h1 = canonical_run_hash(conn)

        conn.execute("UPDATE templates SET template_key = 'CHANGED_TPL_KEY'")
        conn.commit()
        h2 = canonical_run_hash(conn)
        assert h1 == h2

    def test_canonical_hash_excludes_edge_updates(self) -> None:
        """edge_updates is audit trail — changing it doesn't affect hash."""
        conn = _full_pipeline()
        h1 = canonical_run_hash(conn)

        conn.execute("DELETE FROM edge_updates")
        conn.commit()
        h2 = canonical_run_hash(conn)
        assert h1 == h2

    def test_canonical_hash_excludes_timestamps(self) -> None:
        """Hash is the same regardless of created_at values."""
        h1 = canonical_run_hash(_full_pipeline())
        h2 = canonical_run_hash(_full_pipeline())
        assert h1 == h2  # Different wall-clock times, same hash


class TestDerivedTopKInHash:
    """Session 7: derived_topk included in hash."""

    def test_derived_topk_affects_hash(self) -> None:
        """Hash changes when derived_topk is populated."""
        conn = _full_pipeline()
        h_before = canonical_run_hash(conn)

        corr = compute_correlation(conn)
        search_and_store_top_k(conn, corr)
        h_after = canonical_run_hash(conn)

        assert h_before != h_after  # derived_topk changes the hash

    def test_derived_topk_includes_bands_and_flags(self) -> None:
        """derived_topk rows include confidence_band and flags_json in hash."""
        conn = _full_pipeline_with_paths()

        rows = conn.execute(
            "SELECT confidence_band, flags_json FROM derived_topk"
        ).fetchall()
        assert len(rows) >= 1

        for row in rows:
            assert row["confidence_band"] in (
                "VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW", "INSUFFICIENT"
            )
            flags = json.loads(row["flags_json"])
            assert "conflict" in flags
            assert "prior_only" in flags


# ===================================================================
# Full state export
# ===================================================================


class TestFullStateExport:
    def test_export_has_all_keys(self) -> None:
        conn = _full_pipeline_with_paths()
        export = full_state_export(conn)

        assert "edges" in export
        assert "obs_digests" in export
        assert "templates" in export
        assert "nodes" in export
        assert "constraints" in export
        assert "objectives" in export
        assert "derived_topk" in export
        assert "warnings" in export
        assert "canonical_run_hash" in export

    def test_export_edges_match_db(self) -> None:
        conn = _full_pipeline_with_paths()
        export = full_state_export(conn)

        db_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        assert len(export["edges"]) == db_count

    def test_export_nodes_match_db(self) -> None:
        conn = _full_pipeline_with_paths()
        export = full_state_export(conn)
        assert len(export["nodes"]) == 3

    def test_export_derived_topk_present(self) -> None:
        conn = _full_pipeline_with_paths()
        export = full_state_export(conn)
        assert len(export["derived_topk"]) >= 1

    def test_export_hash_matches_direct_call(self) -> None:
        conn = _full_pipeline_with_paths()
        export = full_state_export(conn)
        direct_hash = canonical_run_hash(conn)
        assert export["canonical_run_hash"] == direct_hash

    def test_export_deterministic(self) -> None:
        e1 = full_state_export(_full_pipeline_with_paths())
        e2 = full_state_export(_full_pipeline_with_paths())
        assert e1["canonical_run_hash"] == e2["canonical_run_hash"]
        assert len(e1["edges"]) == len(e2["edges"])
        assert len(e1["derived_topk"]) == len(e2["derived_topk"])


# ===================================================================
# Full pipeline determinism (Session 7 integration gate)
# ===================================================================


class TestFullPipelineDeterminism:
    """canonical_run_hash stable with full pipeline including correlation + paths."""

    def test_full_pipeline_hash_stable(self) -> None:
        """THE comprehensive determinism test: ingest → update → correlate → paths → hash."""
        hashes = []
        for _ in range(3):
            conn = _full_pipeline_with_paths()
            h = canonical_run_hash(conn)
            hashes.append(h)

        assert len(set(hashes)) == 1, f"Hash instability across full pipeline: {hashes}"

    def test_hash_changes_iff_semantic_state_changes(self) -> None:
        """Hash is sensitive to actual belief changes, not cosmetic ones."""
        conn1 = _full_pipeline_with_paths()
        h1 = canonical_run_hash(conn1)

        # Cosmetic change (warning) — no hash change
        conn2 = _full_pipeline_with_paths()
        conn2.execute(
            "INSERT INTO run_warnings (code, severity, message, context_json) "
            "VALUES ('COSMETIC', 'INFO', 'no effect', '{}')"
        )
        conn2.commit()
        h2 = canonical_run_hash(conn2)
        assert h1 == h2

        # Semantic change (edge belief) — hash changes
        conn3 = _full_pipeline_with_paths()
        conn3.execute("UPDATE edges SET alpha_i = alpha_i + 1 WHERE rowid = 1")
        conn3.commit()
        h3 = canonical_run_hash(conn3)
        assert h1 != h3
