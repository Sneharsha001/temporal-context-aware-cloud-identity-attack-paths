"""Tests for ARF-RT storage layer.

Covers:
  - PRAGMA configuration on connect (WAL, foreign_keys, busy_timeout)
  - Migration idempotency
  - Backup API
  - JSON canonical enforcement at write time
  - flags_json canonical shape
  - COLLATE BINARY on TEXT columns
  - Insert/read for all tables
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from arf_rt.config import SQLITE_BUSY_TIMEOUT_MS
from arf_rt.storage.migrations import (
    CURRENT_SCHEMA_VERSION,
    get_current_version,
    run_migrations,
)
from arf_rt.storage.sqlite_store import backup, connect, transaction
from arf_rt.util.canon import (
    canonical_json,
    features_fp,
    make_constraint_id,
    make_constraint_key,
    make_edge_id,
    make_flags_json,
    make_node_id,
    make_objective_id,
    make_template_id,
    make_template_key,
    properties_fp,
)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path):
    c = connect(db_path)
    yield c
    c.close()


# ===================================================================
# PRAGMA tests
# ===================================================================


class TestPragmas:
    """Verify hardened PRAGMAs are set on connect (spec §6.1)."""

    def test_journal_mode_wal(self, conn):
        result = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert result.lower() == "wal"

    def test_foreign_keys_on(self, conn):
        result = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert result == 1

    def test_busy_timeout(self, conn):
        result = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert result == SQLITE_BUSY_TIMEOUT_MS

    def test_synchronous_normal(self, conn):
        result = conn.execute("PRAGMA synchronous").fetchone()[0]
        # NORMAL = 1
        assert result == 1


# ===================================================================
# Migration tests
# ===================================================================


class TestMigrations:
    """Verify migration runner is idempotent and creates all tables."""

    def test_schema_version_after_connect(self, conn):
        assert get_current_version(conn) == CURRENT_SCHEMA_VERSION

    def test_migration_idempotent(self, db_path):
        """Running migrations twice produces the same schema."""
        conn1 = connect(db_path)
        v1 = get_current_version(conn1)
        tables1 = _get_table_names(conn1)
        conn1.close()

        conn2 = connect(db_path)
        v2 = get_current_version(conn2)
        tables2 = _get_table_names(conn2)
        conn2.close()

        assert v1 == v2 == CURRENT_SCHEMA_VERSION
        assert tables1 == tables2

    def test_all_expected_tables_exist(self, conn):
        tables = _get_table_names(conn)
        expected = {
            "schema_version",
            "nodes",
            "templates",
            "edges",
            "constraints",
            "edge_constraints",
            "objectives",
            "observations",
            "edge_updates",
            "run_warnings",
            "derived_topk",
        }
        assert expected.issubset(tables), f"Missing: {expected - tables}"

    def test_schema_version_table_has_entries(self, conn):
        rows = conn.execute("SELECT * FROM schema_version").fetchall()
        assert len(rows) >= 1
        assert rows[-1]["version"] == CURRENT_SCHEMA_VERSION


# ===================================================================
# Backup tests
# ===================================================================


class TestBackup:
    """Verify SQLite backup API creates consistent copies."""

    def test_backup_creates_copy(self, conn, tmp_path):
        # Insert a node
        _insert_test_node(conn)
        conn.commit()

        # Backup
        backup_path = tmp_path / "backup.db"
        backup(conn, backup_path)

        # Verify backup has the node
        conn2 = connect(backup_path, run_migrations_on_connect=False)
        rows = conn2.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        assert rows == 1
        conn2.close()

    def test_backup_is_independent(self, conn, tmp_path):
        _insert_test_node(conn)
        conn.commit()

        backup_path = tmp_path / "backup.db"
        backup(conn, backup_path)

        # Insert another node in source — should NOT appear in backup
        _insert_test_node(conn, provider_id="other")
        conn.commit()

        conn2 = connect(backup_path, run_migrations_on_connect=False)
        rows = conn2.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        assert rows == 1  # Only the first node
        conn2.close()


# ===================================================================
# Transaction tests
# ===================================================================


class TestTransaction:
    """Verify transaction context manager."""

    def test_commit_on_success(self, conn):
        with transaction(conn):
            _insert_test_node(conn)
        rows = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        assert rows == 1

    def test_rollback_on_exception(self, conn):
        with pytest.raises(ValueError):
            with transaction(conn):
                _insert_test_node(conn)
                raise ValueError("oops")
        rows = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        assert rows == 0


# ===================================================================
# Table CRUD tests
# ===================================================================


class TestTableCRUD:
    """Verify insert/read for all tables (integration gate)."""

    def test_insert_read_nodes(self, conn):
        _insert_test_node(conn)
        conn.commit()
        row = conn.execute("SELECT * FROM nodes").fetchone()
        assert row["provider"] == "aws"
        assert row["node_type"] == "identity"

    def test_insert_read_templates(self, conn):
        fp = features_fp({"service": "iam"})
        tid = make_template_id("aws", "assume_role", fp, 1)
        tkey = make_template_key("aws", "assume_role", fp)
        conn.execute(
            """INSERT INTO templates
               (template_id, template_key, provider, edge_type,
                features_json, features_fp, feature_schema_version)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tid, tkey, "aws", "assume_role",
             canonical_json({"service": "iam"}), fp, 1),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM templates").fetchone()
        assert row["template_id"] == tid
        assert row["alpha_agg_i"] == 1

    def test_insert_read_edges(self, conn):
        _insert_full_edge(conn)
        conn.commit()
        row = conn.execute("SELECT * FROM edges").fetchone()
        assert row["alpha_i"] == 1
        assert row["frozen"] == 0
        # Verify flags_json default shape
        flags = json.loads(row["flags_json"])
        assert flags["conflict"] is False

    def test_insert_read_constraints(self, conn):
        pp = properties_fp({"effect": "deny"})
        cid = make_constraint_id("aws", "SCP", "ACCOUNT", "123", "-", pp)
        ckey = make_constraint_key("aws", "SCP", "ACCOUNT", "123", "-", pp)
        conn.execute(
            """INSERT INTO constraints
               (constraint_id, constraint_key, provider, constraint_type,
                scope_type, scope_id, region, properties_json, properties_fp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (cid, ckey, "aws", "SCP", "ACCOUNT", "123", "-",
             canonical_json({"effect": "deny"}), pp),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM constraints").fetchone()
        assert row["constraint_type"] == "SCP"
        assert row["status"] == "ACTIVE"
        assert row["validation_status"] == "UNVALIDATED"

    def test_insert_read_edge_constraints(self, conn):
        eid = _insert_full_edge(conn)
        pp = properties_fp({"effect": "deny"})
        cid = make_constraint_id("aws", "SCP", "ACCOUNT", "123", "-", pp)
        ckey = make_constraint_key("aws", "SCP", "ACCOUNT", "123", "-", pp)
        conn.execute(
            """INSERT INTO constraints
               (constraint_id, constraint_key, provider, constraint_type,
                scope_type, scope_id, region, properties_json, properties_fp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (cid, ckey, "aws", "SCP", "ACCOUNT", "123", "-",
             canonical_json({"effect": "deny"}), pp),
        )
        conn.execute(
            """INSERT INTO edge_constraints (edge_id, constraint_id)
               VALUES (?, ?)""",
            (eid, cid),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM edge_constraints").fetchone()
        assert row["edge_id"] == eid
        assert row["relation_type"] == "APPLIES_TO"

    def test_insert_read_objectives(self, conn):
        oid = make_objective_id("priv_esc", ["node_a"], ["node_c"], 3, 5)
        conn.execute(
            """INSERT INTO objectives
               (objective_id, objective_type, start_nodes_json,
                target_nodes_json, max_depth, k)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (oid, "priv_esc",
             canonical_json(["node_a"]), canonical_json(["node_c"]),
             3, 5),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM objectives").fetchone()
        assert row["max_depth"] == 3
        assert row["k"] == 5

    def test_insert_read_observations(self, conn):
        eid = _insert_full_edge(conn)
        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (eid, "REPLAY_SCRIPTED", "ALLOW", "UNKNOWN", "DIRECT",
             80, 0, 0),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM observations").fetchone()
        assert row["signal_q"] == 80
        assert row["evidence_hash"] is None

    def test_insert_read_edge_updates(self, conn):
        eid = _insert_full_edge(conn)
        conn.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q) VALUES (?, ?, ?, ?, ?, ?)""",
            (eid, "REPLAY_SCRIPTED", "ALLOW", "UNKNOWN", "DIRECT", 80),
        )
        obs_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        fj = make_flags_json()
        conn.execute(
            """INSERT INTO edge_updates
               (edge_id, observation_id, alpha_before, beta_before,
                alpha_after, beta_after, status_before, status_after,
                frozen_before, frozen_after, flags_json_before,
                flags_json_after, polarity, increment)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (eid, obs_id, 1, 1, 77, 1, "HYPOTHESIZED", "HYPOTHESIZED",
             0, 0, fj, fj, "SUPPORT", 76),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM edge_updates").fetchone()
        assert row["alpha_before"] == 1
        assert row["alpha_after"] == 77
        assert row["polarity"] == "SUPPORT"

    def test_insert_read_run_warnings(self, conn):
        conn.execute(
            """INSERT INTO run_warnings (code, severity, message, context_json)
               VALUES (?, ?, ?, ?)""",
            ("DOWNGRADED_DIRECT_NO_EVIDENCE", "WARN",
             "Evidence hash missing", canonical_json({"edge_id": "abc"})),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM run_warnings").fetchone()
        assert row["code"] == "DOWNGRADED_DIRECT_NO_EVIDENCE"

    def test_insert_read_derived_topk(self, conn):
        oid = make_objective_id("pe", ["a"], ["b"], 3, 5)
        conn.execute(
            """INSERT INTO objectives
               (objective_id, objective_type, start_nodes_json,
                target_nodes_json, max_depth, k)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (oid, "pe", canonical_json(["a"]), canonical_json(["b"]), 3, 5),
        )
        conn.execute(
            """INSERT INTO derived_topk
               (objective_id, rank, edge_id_sequence, p_best_q8,
                p_worst_q8, confidence_band, path_length)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (oid, 1, canonical_json(["edge1", "edge2"]),
             90_000_000, 80_000_000, "HIGH", 2),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM derived_topk").fetchone()
        assert row["rank"] == 1
        assert row["confidence_band"] == "HIGH"


# ===================================================================
# Foreign key enforcement
# ===================================================================


class TestForeignKeys:
    """Verify foreign key constraints are enforced."""

    def test_edge_requires_valid_src_node(self, conn):
        fp = features_fp({})
        tid = make_template_id("aws", "assume_role", fp, 1)
        tkey = make_template_key("aws", "assume_role", fp)
        conn.execute(
            """INSERT INTO templates
               (template_id, template_key, provider, edge_type,
                features_json, features_fp, feature_schema_version)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tid, tkey, "aws", "assume_role", "{}", fp, 1),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO edges
                   (edge_id, edge_type, src_node_id, dst_node_id,
                    region, template_id, features_json, features_fp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("eid", "assume_role", "nonexistent_src", "nonexistent_dst",
                 "-", tid, "{}", fp),
            )


# ===================================================================
# CHECK constraint enforcement
# ===================================================================


class TestCheckConstraints:
    """Verify CHECK constraints reject invalid enum values."""

    def test_edge_invalid_status_rejected(self, conn):
        _insert_test_node(conn)
        fp = features_fp({})
        tid = make_template_id("aws", "assume_role", fp, 1)
        tkey = make_template_key("aws", "assume_role", fp)
        conn.execute(
            """INSERT INTO templates
               (template_id, template_key, provider, edge_type,
                features_json, features_fp, feature_schema_version)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tid, tkey, "aws", "assume_role", "{}", fp, 1),
        )
        nid = make_node_id("aws", "identity", "admin", "-")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO edges
                   (edge_id, edge_type, src_node_id, dst_node_id,
                    region, template_id, status, features_json, features_fp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("eid", "assume_role", nid, nid, "-", tid,
                 "INVALID_STATUS", "{}", fp),
            )

    def test_constraint_invalid_type_rejected(self, conn):
        pp = properties_fp({})
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO constraints
                   (constraint_id, constraint_key, provider, constraint_type,
                    scope_type, scope_id, region, properties_json, properties_fp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("cid", "ckey", "aws", "INVALID_TYPE", "ACCOUNT", "123",
                 "-", "{}", pp),
            )

    def test_observation_signal_q_range(self, conn):
        eid = _insert_full_edge(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO observations
                   (edge_id, probe_type, result, reason_class, strength,
                    signal_q)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (eid, "REPLAY_SCRIPTED", "ALLOW", "UNKNOWN", "DIRECT", 101),
            )


# ===================================================================
# COLLATE BINARY tests
# ===================================================================


class TestCollateBinary:
    """Verify COLLATE BINARY ordering in queries."""

    def test_node_ordering_is_binary(self, conn):
        """Binary ordering: uppercase before lowercase (ASCII order)."""
        for pid in ["Zebra", "alpha", "Beta", "gamma"]:
            nid = make_node_id("aws", "identity", pid, "-")
            conn.execute(
                """INSERT INTO nodes
                   (node_id, provider, node_type, provider_id, region)
                   VALUES (?, ?, ?, ?, ?)""",
                (nid, "aws", "identity", pid, "-"),
            )
        conn.commit()

        rows = conn.execute(
            "SELECT node_id FROM nodes ORDER BY node_id COLLATE BINARY"
        ).fetchall()
        ids = [r[0] for r in rows]
        # Verify sorted by binary comparison
        assert ids == sorted(ids)


# ===================================================================
# JSON canonical enforcement test
# ===================================================================


class TestJsonCanonical:
    """Verify JSON stored in DB is canonical."""

    def test_flags_json_default_is_canonical(self, conn):
        eid = _insert_full_edge(conn)
        conn.commit()
        row = conn.execute("SELECT flags_json FROM edges WHERE edge_id = ?",
                           (eid,)).fetchone()
        stored = row["flags_json"]
        reparsed = canonical_json(json.loads(stored))
        assert stored == reparsed

    def test_flags_json_has_all_four_keys(self, conn):
        eid = _insert_full_edge(conn)
        conn.commit()
        row = conn.execute("SELECT flags_json FROM edges WHERE edge_id = ?",
                           (eid,)).fetchone()
        flags = json.loads(row["flags_json"])
        assert set(flags.keys()) == {
            "conflict", "counterfactual_override", "prior_only", "stale"
        }


# ===================================================================
# Helpers
# ===================================================================


def _get_table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r[0] for r in rows}


def _insert_test_node(
    conn: sqlite3.Connection,
    provider: str = "aws",
    node_type: str = "identity",
    provider_id: str = "admin",
    region: str = "-",
) -> str:
    nid = make_node_id(provider, node_type, provider_id, region)
    conn.execute(
        """INSERT OR IGNORE INTO nodes
           (node_id, provider, node_type, provider_id, region)
           VALUES (?, ?, ?, ?, ?)""",
        (nid, provider, node_type, provider_id, region),
    )
    return nid


def _insert_full_edge(conn: sqlite3.Connection) -> str:
    """Insert a node, template, and edge. Returns edge_id."""
    nid = _insert_test_node(conn)
    fp = features_fp({})
    tid = make_template_id("aws", "assume_role", fp, 1)
    tkey = make_template_key("aws", "assume_role", fp)
    conn.execute(
        """INSERT OR IGNORE INTO templates
           (template_id, template_key, provider, edge_type,
            features_json, features_fp, feature_schema_version)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (tid, tkey, "aws", "assume_role", canonical_json({}), fp, 1),
    )
    eid = make_edge_id("assume_role", nid, nid, "-", tid)
    fj = make_flags_json(prior_only=True)
    conn.execute(
        """INSERT OR IGNORE INTO edges
           (edge_id, edge_type, src_node_id, dst_node_id,
            region, template_id, flags_json, features_json, features_fp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (eid, "assume_role", nid, nid, "-", tid, fj, canonical_json({}), fp),
    )
    return eid
