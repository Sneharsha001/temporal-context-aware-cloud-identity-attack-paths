"""Tests for Session 15 scaffolding: SAFE mode executor + call logging."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arf_rt.adapters.scenario_builder import build_scenario
from arf_rt.adapters.pmapper import translate_from_file
from arf_rt.cli import run_full_pipeline
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.executor import ProbeExecutor, ProbeResult, ensure_call_log_table
from arf_rt.engine.planner import plan_probes

PMAPPER = str(Path(__file__).parent.parent / "fixtures" / "planner_pmapper.json")
ORG = str(Path(__file__).parent.parent / "fixtures" / "demo_aws_org.json")


@pytest.fixture(scope="module")
def executor_env():
    """Build planner scenario, run pipeline, get plan result."""
    translated = translate_from_file(PMAPPER)
    edge_map = {}
    for e in translated.edges:
        src = e["src"]["provider_id"].split("/")[-1]
        dst = e["dst"]["provider_id"].split("/")[-1]
        edge_map[f"{src}->{dst}"] = e

    observations = []
    for name, obs_list in [
        ("attacker->JumpRole", [("ALLOW", "UNKNOWN", 90, "ev1"), ("ALLOW", "UNKNOWN", 85, "ev2")]),
        ("JumpRole->ProdDeploy", [("ALLOW", "UNKNOWN", 85, "ev3")]),
        ("ProdDeploy->ProdAdmin", [("DENY", "CONSTRAINT_DENY", 95, "ev4")]),
    ]:
        edge = edge_map[name]
        for result, reason, sq, ev in obs_list:
            observations.append({
                "edge_ref": {"edge_type": edge["edge_type"], "src": edge["src"],
                             "dst": edge["dst"], "region": edge.get("region", "-")},
                "probe_type": "REPLAY_SCRIPTED", "result": result,
                "reason_class": reason, "strength": "DIRECT", "signal_q": sq,
                "is_counterfactual": False,
                "constraint_relevant": name == "ProdDeploy->ProdAdmin",
                "evidence_hash": ev,
            })

    objectives = [{
        "objective_type": "REACHABILITY",
        "start_nodes": [translated.nodes[0]],
        "target_nodes": [translated.nodes[3]],
        "max_depth": 5, "k": 10,
    }]

    scenario = build_scenario(PMAPPER, org_path=ORG,
                              objectives=objectives, observations=observations)
    tmp = Path("/tmp/executor_test.json")
    with open(tmp, "w") as f:
        json.dump(scenario, f, indent=2)

    conn, _ = run_full_pipeline(str(tmp))
    corr = compute_correlation(conn)
    plan = plan_probes(conn, corr)
    return conn, plan


# ===================================================================
# DRY_RUN mode
# ===================================================================


class TestDryRun:
    def test_dry_run_logs_all_candidates(self, executor_env):
        conn, plan = executor_env
        executor = ProbeExecutor(conn, mode="DRY_RUN")
        results = executor.execute_plan(plan)
        assert len(results) == len(plan["candidates"])

    def test_dry_run_all_logged(self, executor_env):
        conn, plan = executor_env
        executor = ProbeExecutor(conn, mode="DRY_RUN")
        results = executor.execute_plan(plan)
        for r in results:
            assert r.disposition == "LOGGED"
            assert r.result is None
            assert r.error_message is None
            assert r.log_id is not None

    def test_dry_run_populates_call_log(self, executor_env):
        conn, plan = executor_env
        executor = ProbeExecutor(conn, mode="DRY_RUN")
        executor.execute_plan(plan)
        log = executor.get_call_log()
        assert len(log) >= len(plan["candidates"])

    def test_dry_run_call_log_has_edge_details(self, executor_env):
        conn, plan = executor_env
        executor = ProbeExecutor(conn, mode="DRY_RUN")
        executor.execute_plan(plan)
        log = executor.get_call_log()
        for entry in log:
            assert entry["edge_id"] is not None
            assert entry["action"] is not None
            assert entry["mode"] == "DRY_RUN"
            assert entry["requested_at"] is not None

    def test_dry_run_captures_eig(self, executor_env):
        conn, plan = executor_env
        executor = ProbeExecutor(conn, mode="DRY_RUN")
        executor.execute_plan(plan)
        log = executor.get_call_log()
        for entry in log:
            assert entry["eig_score"] is not None
            assert entry["eig_score"] >= 0

    def test_dry_run_captures_reasons(self, executor_env):
        conn, plan = executor_env
        executor = ProbeExecutor(conn, mode="DRY_RUN")
        executor.execute_plan(plan)
        log = executor.get_call_log()
        for entry in log:
            reasons = json.loads(entry["reasons_json"])
            assert isinstance(reasons, list)
            assert len(reasons) >= 1


# ===================================================================
# CONFIRM mode
# ===================================================================


class TestConfirmMode:
    def test_confirm_approved(self, executor_env):
        conn, plan = executor_env
        executor = ProbeExecutor(conn, mode="CONFIRM", confirm_fn=lambda *a: True)
        results = executor.execute_plan(plan)
        for r in results:
            assert r.disposition == "APPROVED"

    def test_confirm_skipped(self, executor_env):
        conn, plan = executor_env
        executor = ProbeExecutor(conn, mode="CONFIRM", confirm_fn=lambda *a: False)
        results = executor.execute_plan(plan)
        for r in results:
            assert r.disposition == "SKIPPED"

    def test_confirm_selective(self, executor_env):
        """Approve first candidate, skip the rest."""
        conn, plan = executor_env
        first_eid = plan["candidates"][0]["edge_id"]
        executor = ProbeExecutor(
            conn, mode="CONFIRM",
            confirm_fn=lambda eid, *a: eid == first_eid,
        )
        results = executor.execute_plan(plan)
        assert results[0].disposition == "APPROVED"
        for r in results[1:]:
            assert r.disposition == "SKIPPED"

    def test_confirm_fn_receives_edge_details(self, executor_env):
        """Confirm function receives edge_id, action, target_arn, eig."""
        conn, plan = executor_env
        received = []

        def capture(*args):
            received.append(args)
            return False

        executor = ProbeExecutor(conn, mode="CONFIRM", confirm_fn=capture)
        executor.execute_plan(plan)
        assert len(received) == len(plan["candidates"])
        for args in received:
            assert len(args) == 4  # edge_id, action, target_arn, eig
            assert isinstance(args[3], float)  # eig is float


# ===================================================================
# LIVE mode (not implemented)
# ===================================================================


class TestLiveMode:
    def test_live_fails_gracefully(self, executor_env):
        conn, plan = executor_env
        executor = ProbeExecutor(conn, mode="LIVE")
        results = executor.execute_plan(plan)
        for r in results:
            assert r.disposition == "FAILED"
            assert "not yet implemented" in r.error_message


# ===================================================================
# Invalid mode
# ===================================================================


class TestInvalidMode:
    def test_invalid_mode_raises(self, executor_env):
        conn, _ = executor_env
        with pytest.raises(ValueError, match="Invalid mode"):
            ProbeExecutor(conn, mode="YOLO")


# ===================================================================
# Call log summary
# ===================================================================


class TestCallLogSummary:
    def test_summary_counts(self, executor_env):
        conn, plan = executor_env
        # Clear any previous log entries
        conn.execute("DELETE FROM call_log")
        conn.commit()

        executor = ProbeExecutor(conn, mode="DRY_RUN")
        executor.execute_plan(plan)
        summary = executor.get_call_log_summary()
        assert summary["LOGGED"] == len(plan["candidates"])

    def test_mixed_summary(self, executor_env):
        conn, plan = executor_env
        conn.execute("DELETE FROM call_log")
        conn.commit()

        # DRY_RUN some
        dry = ProbeExecutor(conn, mode="DRY_RUN")
        dry.execute_probe(plan["candidates"][0])

        # CONFIRM + skip some
        confirm = ProbeExecutor(conn, mode="CONFIRM", confirm_fn=lambda *a: False)
        confirm.execute_probe(plan["candidates"][1])

        summary = dry.get_call_log_summary()
        assert summary.get("LOGGED", 0) == 1
        assert summary.get("SKIPPED", 0) == 1


# ===================================================================
# ProbeResult
# ===================================================================


class TestProbeResult:
    def test_to_dict(self):
        r = ProbeResult("edge123", "LOGGED", log_id=42)
        d = r.to_dict()
        assert d["edge_id"] == "edge123"
        assert d["disposition"] == "LOGGED"
        assert d["log_id"] == 42
        assert d["result"] is None
        assert d["error_message"] is None


# ===================================================================
# Run hash traceability
# ===================================================================


class TestRunHash:
    def test_run_hash_stored_in_call_log(self, executor_env):
        conn, plan = executor_env
        conn.execute("DELETE FROM call_log")
        conn.commit()

        executor = ProbeExecutor(conn, mode="DRY_RUN", run_hash="abc123deadbeef")
        executor.execute_plan(plan)
        log = executor.get_call_log()
        for entry in log:
            assert entry["run_hash"] == "abc123deadbeef"

    def test_run_hash_none_when_not_provided(self, executor_env):
        conn, plan = executor_env
        conn.execute("DELETE FROM call_log")
        conn.commit()

        executor = ProbeExecutor(conn, mode="DRY_RUN")
        executor.execute_plan(plan)
        log = executor.get_call_log()
        for entry in log:
            assert entry["run_hash"] is None

    def test_run_hash_from_canonical_hash(self, executor_env):
        """Typical usage: pass canonical_run_hash as run_hash."""
        conn, plan = executor_env
        conn.execute("DELETE FROM call_log")
        conn.commit()

        from arf_rt.engine.snapshot import canonical_run_hash
        h = canonical_run_hash(conn)
        executor = ProbeExecutor(conn, mode="DRY_RUN", run_hash=h)
        executor.execute_plan(plan)
        log = executor.get_call_log()
        assert log[0]["run_hash"] == h
        assert len(h) == 64  # SHA-256 hex
