"""Tests for adapters/replay.py and adapters/seed_json.py (spec §18)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arf_rt.adapters.replay import ReplayAdapter
from arf_rt.adapters.seed_json import (
    load_scenario_dict,
    load_scenario_file,
    load_scenario_string,
)
from arf_rt.engine import feature_schema_registry
from arf_rt.storage.sqlite_store import connect
from arf_rt.util.canon import (
    ARFValidationError,
    canonical_json,
    features_fp as compute_features_fp,
    make_constraint_id,
    make_edge_id,
    make_node_id,
    make_objective_id,
    make_template_id,
    properties_fp as compute_properties_fp,
    region_norm,
)


FIXTURES = Path(__file__).parent.parent / "fixtures"
MINIMAL_SCENARIO = FIXTURES / "minimal_scenario.json"


# ===================================================================
# Helpers
# ===================================================================


def _load_minimal() -> dict:
    return json.loads(MINIMAL_SCENARIO.read_text())


def _in_memory_db():
    return connect(":memory:")


def _ingest_minimal():
    """Ingest minimal scenario, return (conn, warnings)."""
    conn = _in_memory_db()
    scenario = load_scenario_file(MINIMAL_SCENARIO)
    adapter = ReplayAdapter(conn)
    warnings = adapter.ingest(scenario)
    return conn, warnings


def _ingest_minimal_with_adapter():
    """Ingest minimal scenario, return (conn, adapter, warnings)."""
    conn = _in_memory_db()
    scenario = load_scenario_file(MINIMAL_SCENARIO)
    adapter = ReplayAdapter(conn)
    warnings = adapter.ingest(scenario)
    return conn, adapter, warnings


# Pre-computed expected IDs for the minimal scenario
_NODE_A_ID = make_node_id("aws", "IAMRole", "role-alpha", "us-east-1")
_NODE_B_ID = make_node_id("aws", "IAMRole", "role-bravo", "us-east-1")
_NODE_C_ID = make_node_id("aws", "IAMRole", "role-charlie", "us-east-1")

_FEAT = {"action": "sts:AssumeRole", "effect": "Allow"}
_FEAT_FP = compute_features_fp(_FEAT)
_TEMPLATE_ID = make_template_id("aws", "sts:AssumeRole", _FEAT_FP, 1)

_EDGE_AB_ID = make_edge_id(
    "sts:AssumeRole", _NODE_A_ID, _NODE_B_ID, "us-east-1", _TEMPLATE_ID
)
_EDGE_BC_ID = make_edge_id(
    "sts:AssumeRole", _NODE_B_ID, _NODE_C_ID, "us-east-1", _TEMPLATE_ID
)

_CST_PROPS = {"action": "sts:AssumeRole", "effect": "Deny"}
_CST_PROP_FP = compute_properties_fp(_CST_PROPS)
_CONSTRAINT_ID = make_constraint_id(
    "aws", "SCP", "OU", "ou-root-001", "us-east-1", _CST_PROP_FP
)

_OBJECTIVE_ID = make_objective_id(
    "REACHABILITY",
    [_NODE_A_ID],
    [_NODE_C_ID],
    3,
    3,
)


# ===================================================================
# seed_json tests
# ===================================================================


class TestSeedJson:
    """Tests for scenario loading and validation."""

    def test_load_file(self) -> None:
        scenario = load_scenario_file(MINIMAL_SCENARIO)
        assert len(scenario.nodes) == 3
        assert len(scenario.edges) == 2
        assert len(scenario.objectives) == 1

    def test_load_string(self) -> None:
        raw = MINIMAL_SCENARIO.read_text()
        scenario = load_scenario_string(raw)
        assert len(scenario.nodes) == 3

    def test_load_dict(self) -> None:
        data = _load_minimal()
        scenario = load_scenario_dict(data)
        assert len(scenario.edges) == 2

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(ARFValidationError, match="Invalid JSON"):
            load_scenario_string("{bad json")

    def test_non_dict_raises(self) -> None:
        with pytest.raises(ARFValidationError, match="JSON object"):
            load_scenario_dict([1, 2, 3])

    def test_missing_file_raises(self) -> None:
        with pytest.raises(ARFValidationError, match="not found"):
            load_scenario_file("/nonexistent/path.json")

    def test_extra_field_rejected(self) -> None:
        data = _load_minimal()
        data["bogus_field"] = "should fail"
        with pytest.raises(Exception):
            load_scenario_dict(data)

    def test_signal_q_float_rejected(self) -> None:
        """Spec §18.3: signal_q must be int, floats rejected."""
        data = _load_minimal()
        data["observations"][0]["signal_q"] = 80.5
        with pytest.raises(Exception):
            load_scenario_dict(data)

    def test_no_objectives_rejected(self) -> None:
        data = _load_minimal()
        data["objectives"] = []
        with pytest.raises(Exception):
            load_scenario_dict(data)


# ===================================================================
# Replay ingest tests
# ===================================================================


class TestReplayIngest:
    """Integration tests for full scenario ingest."""

    def test_ingest_creates_all_rows(self) -> None:
        """All tables populated after ingest."""
        conn, warnings = _ingest_minimal()

        nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        assert nodes == 3

        edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        assert edges == 2

        templates = conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
        assert templates >= 1

        constraints = conn.execute("SELECT COUNT(*) FROM constraints").fetchone()[0]
        assert constraints == 1

        ec = conn.execute("SELECT COUNT(*) FROM edge_constraints").fetchone()[0]
        assert ec == 2

        objectives = conn.execute("SELECT COUNT(*) FROM objectives").fetchone()[0]
        assert objectives == 1

        obs = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        assert obs == 3

    def test_node_id_deterministic(self) -> None:
        """Node IDs match hand-computed values."""
        conn, _ = _ingest_minimal()

        row = conn.execute(
            "SELECT node_id FROM nodes WHERE provider_id = ?",
            ("role-alpha",),
        ).fetchone()
        assert row["node_id"] == _NODE_A_ID

        row = conn.execute(
            "SELECT node_id FROM nodes WHERE provider_id = ?",
            ("role-bravo",),
        ).fetchone()
        assert row["node_id"] == _NODE_B_ID

        row = conn.execute(
            "SELECT node_id FROM nodes WHERE provider_id = ?",
            ("role-charlie",),
        ).fetchone()
        assert row["node_id"] == _NODE_C_ID

    def test_edge_id_deterministic(self) -> None:
        """Edge IDs match hand-computed values."""
        conn, _ = _ingest_minimal()

        rows = conn.execute(
            "SELECT edge_id, src_node_id, dst_node_id FROM edges ORDER BY edge_id COLLATE BINARY"
        ).fetchall()
        edge_ids = {r["edge_id"] for r in rows}
        assert _EDGE_AB_ID in edge_ids
        assert _EDGE_BC_ID in edge_ids

    def test_template_created(self) -> None:
        conn, _ = _ingest_minimal()
        row = conn.execute(
            "SELECT template_id, features_fp FROM templates WHERE template_id = ?",
            (_TEMPLATE_ID,),
        ).fetchone()
        assert row is not None
        assert row["features_fp"] == _FEAT_FP

    def test_constraint_id_deterministic(self) -> None:
        conn, _ = _ingest_minimal()
        row = conn.execute(
            "SELECT constraint_id FROM constraints WHERE constraint_id = ?",
            (_CONSTRAINT_ID,),
        ).fetchone()
        assert row is not None

    def test_edge_constraints_linked(self) -> None:
        """Both edges linked to the SCP constraint."""
        conn, _ = _ingest_minimal()
        rows = conn.execute(
            "SELECT edge_id FROM edge_constraints WHERE constraint_id = ? "
            "ORDER BY edge_id COLLATE BINARY",
            (_CONSTRAINT_ID,),
        ).fetchall()
        edge_ids = {r["edge_id"] for r in rows}
        assert _EDGE_AB_ID in edge_ids
        assert _EDGE_BC_ID in edge_ids

    def test_objective_deterministic(self) -> None:
        conn, _ = _ingest_minimal()
        row = conn.execute(
            "SELECT objective_id, objective_type, max_depth, k FROM objectives"
        ).fetchone()
        assert row["objective_id"] == _OBJECTIVE_ID
        assert row["objective_type"] == "REACHABILITY"
        assert row["max_depth"] == 3
        assert row["k"] == 3

    def test_objective_node_lists_sorted(self) -> None:
        conn, _ = _ingest_minimal()
        row = conn.execute(
            "SELECT start_nodes_json, target_nodes_json FROM objectives"
        ).fetchone()
        start = json.loads(row["start_nodes_json"])
        target = json.loads(row["target_nodes_json"])
        assert start == sorted(start)
        assert target == sorted(target)

    def test_observations_inserted(self) -> None:
        conn, _ = _ingest_minimal()
        rows = conn.execute(
            "SELECT edge_id, result, strength, signal_q, evidence_hash "
            "FROM observations ORDER BY observation_id"
        ).fetchall()
        assert len(rows) == 3

        # First: ALLOW on A→B, DIRECT, signal_q=80, evidence_hash=abc123
        assert rows[0]["edge_id"] == _EDGE_AB_ID
        assert rows[0]["result"] == "ALLOW"
        assert rows[0]["strength"] == "DIRECT"
        assert rows[0]["signal_q"] == 80
        assert rows[0]["evidence_hash"] == "abc123"

        # Second: DENY on B→C, DIRECT, signal_q=90
        assert rows[1]["edge_id"] == _EDGE_BC_ID
        assert rows[1]["result"] == "DENY"
        assert rows[1]["strength"] == "DIRECT"

        # Third: ALLOW on A→B — was DIRECT but no evidence_hash → INFERRED
        assert rows[2]["edge_id"] == _EDGE_AB_ID
        assert rows[2]["result"] == "ALLOW"
        assert rows[2]["strength"] == "INFERRED"  # downgraded!
        assert rows[2]["evidence_hash"] is None


class TestStrengthDowngrade:
    """Spec §18.4: DIRECT without evidence_hash → INFERRED + warning."""

    def test_downgrade_writes_warning(self) -> None:
        conn, warnings = _ingest_minimal()
        downgrade_warnings = [
            w for w in warnings if w["code"] == "DOWNGRADED_DIRECT_NO_EVIDENCE"
        ]
        assert len(downgrade_warnings) == 1
        assert "edge_id" in downgrade_warnings[0]["context"]

    def test_warning_in_db(self) -> None:
        conn, _ = _ingest_minimal()
        rows = conn.execute(
            "SELECT code, severity, message FROM run_warnings "
            "WHERE code = 'DOWNGRADED_DIRECT_NO_EVIDENCE'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["severity"] == "WARN"

    def test_no_downgrade_with_evidence_hash(self) -> None:
        """DIRECT + evidence_hash stays DIRECT."""
        conn, _ = _ingest_minimal()
        row = conn.execute(
            "SELECT strength FROM observations WHERE evidence_hash = 'abc123'"
        ).fetchone()
        assert row["strength"] == "DIRECT"


class TestEdgeFlagsOnIngest:
    """Edges should have prior_only=true after ingest (no observations applied yet)."""

    def test_prior_only_flag_set(self) -> None:
        conn, _ = _ingest_minimal()
        rows = conn.execute("SELECT flags_json FROM edges").fetchall()
        for row in rows:
            flags = json.loads(row["flags_json"])
            assert flags["prior_only"] is True
            assert flags["conflict"] is False


class TestEdgeRefResolutionIndexes:
    """Replay edge refs should resolve through deterministic indexes."""

    def test_exact_edge_id_resolves(self) -> None:
        _, adapter, _ = _ingest_minimal_with_adapter()
        assert adapter._resolve_edge_ref(_EDGE_AB_ID) == _EDGE_AB_ID
        assert adapter._resolve_edge_ref({"edge_id": _EDGE_AB_ID}) == _EDGE_AB_ID

    def test_unique_short_prefix_resolves(self) -> None:
        _, adapter, _ = _ingest_minimal_with_adapter()
        other_ids = {_EDGE_BC_ID}
        prefix = next(
            _EDGE_AB_ID[:i]
            for i in range(1, len(_EDGE_AB_ID) + 1)
            if not any(edge_id.startswith(_EDGE_AB_ID[:i]) for edge_id in other_ids)
        )

        assert adapter._resolve_edge_ref(prefix) == _EDGE_AB_ID
        assert adapter._edge_ref_scan_fallbacks == 0

    def test_ambiguous_short_prefix_raises(self) -> None:
        adapter = ReplayAdapter(_in_memory_db())
        adapter._index_edge_id("abc" + "0" * 61)
        adapter._index_edge_id("abc" + "1" * 61)

        with pytest.raises(ARFValidationError, match="Ambiguous edge_id prefix"):
            adapter._resolve_edge_ref("abc")

    def test_structured_ref_resolves_without_scanning_edge_map(self) -> None:
        _, adapter, _ = _ingest_minimal_with_adapter()

        class NoItemsDict(dict):
            def items(self):  # type: ignore[override]
                raise AssertionError("structured refs should not scan _edge_map")

        adapter._edge_map = NoItemsDict(adapter._edge_map)
        ref = {
            "edge_type": "sts:AssumeRole",
            "src": {
                "provider": "aws",
                "node_type": "IAMRole",
                "provider_id": "role-alpha",
                "region": "us-east-1",
            },
            "dst": {
                "provider": "aws",
                "node_type": "IAMRole",
                "provider_id": "role-bravo",
                "region": "us-east-1",
            },
            "region": "us-east-1",
        }

        assert adapter._resolve_edge_ref(ref) == _EDGE_AB_ID
        assert adapter._edge_ref_scan_fallbacks == 0

    def test_50k_edge_prefix_resolution_avoids_per_ref_scans(self) -> None:
        adapter = ReplayAdapter(_in_memory_db())
        edge_ids = [f"{i:012x}" + "a" * 52 for i in range(50_000)]
        for edge_id in edge_ids:
            adapter._index_edge_id(edge_id)

        for edge_id in edge_ids[::3]:
            assert adapter._resolve_edge_ref(edge_id[:12]) == edge_id

        assert adapter._edge_ref_scan_fallbacks == 0
        assert set(adapter._edge_prefix_indexes) == {12}


class TestIngestIdempotent:
    """Ingesting the same scenario twice should not create duplicates."""

    def test_double_ingest_same_counts(self) -> None:
        conn = _in_memory_db()
        scenario = load_scenario_file(MINIMAL_SCENARIO)
        adapter = ReplayAdapter(conn)
        adapter.ingest(scenario)

        # Second ingest
        adapter2 = ReplayAdapter(conn)
        adapter2.ingest(scenario)

        # Nodes, edges, templates, constraints, objectives all use INSERT OR IGNORE
        assert conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM constraints").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM objectives").fetchone()[0] == 1

        # Observations DO duplicate (they're append-only events)
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 6


class TestIngestDeterminism:
    """Same scenario → same IDs every time."""

    def test_node_ids_stable_across_runs(self) -> None:
        conn1, _ = _ingest_minimal()
        conn2, _ = _ingest_minimal()

        ids1 = {r["node_id"] for r in conn1.execute("SELECT node_id FROM nodes")}
        ids2 = {r["node_id"] for r in conn2.execute("SELECT node_id FROM nodes")}
        assert ids1 == ids2

    def test_edge_ids_stable_across_runs(self) -> None:
        conn1, _ = _ingest_minimal()
        conn2, _ = _ingest_minimal()

        ids1 = {r["edge_id"] for r in conn1.execute("SELECT edge_id FROM edges")}
        ids2 = {r["edge_id"] for r in conn2.execute("SELECT edge_id FROM edges")}
        assert ids1 == ids2


# ===================================================================
# Feature schema registry tests
# ===================================================================


class TestFeatureSchemaRegistry:
    """Tests for engine/feature_schema_registry.py."""

    def setup_method(self) -> None:
        feature_schema_registry.clear()

    def test_register_and_lookup(self) -> None:
        feature_schema_registry.register("aws", "sts:AssumeRole", 1, {"action", "effect"})
        keys = feature_schema_registry.get_required_keys("aws", "sts:AssumeRole", 1)
        assert keys == frozenset({"action", "effect"})

    def test_unregistered_returns_none(self) -> None:
        assert feature_schema_registry.get_required_keys("aws", "bogus", 1) is None

    def test_idempotent_same_keys(self) -> None:
        feature_schema_registry.register("aws", "sts:AssumeRole", 1, {"action"})
        feature_schema_registry.register("aws", "sts:AssumeRole", 1, {"action"})

    def test_conflict_raises(self) -> None:
        feature_schema_registry.register("aws", "sts:AssumeRole", 1, {"action"})
        with pytest.raises(ARFValidationError, match="already registered"):
            feature_schema_registry.register("aws", "sts:AssumeRole", 1, {"other"})

    def test_validate_features_passes(self) -> None:
        feature_schema_registry.register("aws", "sts:AssumeRole", 1, {"action", "effect"})
        missing = feature_schema_registry.validate_features(
            "aws", "sts:AssumeRole", 1, {"action": "x", "effect": "y", "extra": "z"}
        )
        assert missing == []

    def test_validate_features_missing(self) -> None:
        feature_schema_registry.register("aws", "sts:AssumeRole", 1, {"action", "effect"})
        missing = feature_schema_registry.validate_features(
            "aws", "sts:AssumeRole", 1, {"action": "x"}
        )
        assert missing == ["effect"]

    def test_validate_no_schema_passes(self) -> None:
        """No schema registered = anything goes."""
        missing = feature_schema_registry.validate_features(
            "aws", "bogus", 1, {"whatever": True}
        )
        assert missing == []

    def test_required_keys_stable(self) -> None:
        """Spec test: test_feature_schema_registry_required_keys_stable."""
        feature_schema_registry.register("aws", "sts:AssumeRole", 1, {"action", "effect"})
        k1 = feature_schema_registry.get_required_keys("aws", "sts:AssumeRole", 1)
        k2 = feature_schema_registry.get_required_keys("aws", "sts:AssumeRole", 1)
        assert k1 == k2
        assert isinstance(k1, frozenset)
