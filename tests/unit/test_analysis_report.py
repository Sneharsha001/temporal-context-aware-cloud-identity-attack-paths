"""Tests for analysis report generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arf_rt.adapters.scenario_builder import build_scenario
from arf_rt.adapters.pmapper import translate_from_file
from arf_rt.cli import run_full_pipeline
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.executor import ProbeExecutor
from arf_rt.engine.planner import plan_probes
from arf_rt.engine.snapshot import canonical_run_hash
from arf_rt.reporting.analysis_report import (
    _pluralize,
    component_label,
    edge_name,
    generate_analysis_report,
    mechanism_text,
)

PMAPPER = str(Path(__file__).parent.parent / "fixtures" / "realistic_pmapper.json")
ORG = str(Path(__file__).parent.parent / "fixtures" / "realistic_aws_org.json")


@pytest.fixture(scope="module")
def report_env():
    """Build realistic scenario, run pipeline, return all artifacts."""
    translated = translate_from_file(PMAPPER)
    edge_map = {}
    for e in translated.edges:
        src = e["src"]["provider_id"].split("/")[-1]
        dst = e["dst"]["provider_id"].split("/")[-1]
        edge_map[f"{src}->{dst}"] = e

    observations = []
    for name, obs_list in [
        ("attacker->DevOps", [("ALLOW", "UNKNOWN", 95, "pt-1"), ("ALLOW", "UNKNOWN", 90, "pt-2")]),
        ("DevOps->CI-Runner", [("ALLOW", "UNKNOWN", 85, "pt-3")]),
        ("DevOps->LambdaDeploy", [("ALLOW", "UNKNOWN", 80, "pt-4")]),
        ("CI-Runner->StagingDeploy", [("ALLOW", "UNKNOWN", 90, "pt-5")]),
        ("LambdaDeploy->StagingDeploy", [("ALLOW", "UNKNOWN", 85, "pt-6")]),
        ("StagingDeploy->StagingAdmin", [("DENY", "CONSTRAINT_DENY", 95, "pt-7")]),
        ("StagingDeploy->ProdDeploy", [("ALLOW", "UNKNOWN", 60, "pt-8")]),
        ("attacker->EC2Bastion", [("ALLOW", "UNKNOWN", 70, "pt-9")]),
        ("EC2Bastion->SharedInfra", [("ALLOW", "UNKNOWN", 50, "pt-10")]),
        ("ProdDeploy->ProdApp", [("DENY", "CONSTRAINT_DENY", 90, "pt-11")]),
    ]:
        edge = edge_map[name]
        for result, reason, sq, ev in obs_list:
            observations.append({
                "edge_ref": {"edge_type": edge["edge_type"], "src": edge["src"],
                             "dst": edge["dst"], "region": edge.get("region", "-")},
                "probe_type": "REPLAY_SCRIPTED", "result": result, "reason_class": reason,
                "strength": "DIRECT", "signal_q": sq, "is_counterfactual": False,
                "constraint_relevant": "DENY" in result, "evidence_hash": ev,
            })

    objectives = [{"objective_type": "REACHABILITY", "start_nodes": [translated.nodes[0]],
                    "target_nodes": [translated.nodes[11]], "max_depth": 8, "k": 10}]

    scenario = build_scenario(PMAPPER, org_path=ORG,
                              objectives=objectives, observations=observations)
    tmp = Path("/tmp/report_test.json")
    with open(tmp, "w") as f:
        json.dump(scenario, f, indent=2)

    conn, _ = run_full_pipeline(str(tmp))
    corr = compute_correlation(conn)
    plan = plan_probes(conn, corr)
    run_hash = canonical_run_hash(conn)
    executor = ProbeExecutor(conn, mode="DRY_RUN", run_hash=run_hash)
    executor.execute_plan(plan)
    exec_summary = executor.get_call_log_summary()

    return conn, corr, plan, run_hash, exec_summary


class TestPluralize:
    def test_singular(self):
        assert _pluralize(1, "edge") == "1 edge"

    def test_plural(self):
        assert _pluralize(6, "edge") == "6 edges"

    def test_zero(self):
        assert _pluralize(0, "edge") == "0 edges"

    def test_custom_plural(self):
        assert _pluralize(1, "edge linkage") == "1 edge linkage"
        assert _pluralize(3, "edge linkage") == "3 edge linkages"


class TestMechanismText:
    def test_scp(self):
        text = mechanism_text("SCP")
        assert "SCP" in text
        assert "Service Control Policy" in text
        assert "trust" not in text.lower()

    def test_trust_condition(self):
        text = mechanism_text("TRUST_CONDITION")
        assert "trust" in text.lower()
        assert "SCP" not in text

    def test_other(self):
        text = mechanism_text("UNKNOWN")
        assert "Uncorrelated" in text


class TestEdgeName:
    def test_valid_edge(self, report_env):
        conn, *_ = report_env
        eid = conn.execute("SELECT edge_id FROM edges LIMIT 1").fetchone()["edge_id"]
        name = edge_name(conn, eid)
        assert "→" in name
        assert len(name) > 3

    def test_missing_edge(self, report_env):
        conn, *_ = report_env
        name = edge_name(conn, "nonexistent_edge_id_12345")
        assert "..." in name


class TestGenerateReport:
    def test_report_is_string(self, report_env):
        conn, corr, plan, run_hash, exec_summary = report_env
        report = generate_analysis_report(conn, corr, plan, run_hash, exec_summary)
        assert isinstance(report, str)
        assert len(report) > 1000

    def test_report_has_all_sections(self, report_env):
        conn, corr, plan, run_hash, exec_summary = report_env
        report = generate_analysis_report(conn, corr, plan, run_hash, exec_summary)
        for section in ["Environment", "Constraints", "Edge Beliefs",
                        "Correlation Groups", "Paths Found",
                        "Probe Recommendations", "Reproducibility"]:
            assert f"## {section}" in report

    def test_no_grammar_bug_linkages(self, report_env):
        """'1 edge linkage' not '1 edge linkages'."""
        conn, corr, plan, run_hash, exec_summary = report_env
        report = generate_analysis_report(conn, corr, plan, run_hash, exec_summary)
        assert "1 edge linkages" not in report

    def test_scp_mechanism_not_on_trust(self, report_env):
        """TRUST_CONDITION components must not say 'SCP governance'."""
        conn, corr, plan, run_hash, exec_summary = report_env
        report = generate_analysis_report(conn, corr, plan, run_hash, exec_summary)
        # Find trust sections and check they don't mention SCP governance
        lines = report.split("\n")
        in_trust = False
        for line in lines:
            if "Trust:" in line and "**" in line:
                in_trust = True
            elif "**" in line and "Trust:" not in line:
                in_trust = False
            if in_trust and "SCP governance" in line:
                pytest.fail(f"Trust component incorrectly says 'SCP governance': {line}")

    def test_component_summary_readable(self, report_env):
        """Component summary should use human labels, not raw signatures."""
        conn, corr, plan, run_hash, exec_summary = report_env
        report = generate_analysis_report(conn, corr, plan, run_hash, exec_summary)
        # Should NOT contain raw JSON arrays in component summary
        lines = report.split("\n")
        in_summary = False
        for line in lines:
            if "### Component Summary" in line:
                in_summary = True
            elif line.startswith("##") and "Component Summary" not in line:
                in_summary = False
            if in_summary and line.startswith("|") and "[[" in line:
                pytest.fail(f"Raw signature in component summary: {line}")

    def test_run_hash_present(self, report_env):
        conn, corr, plan, run_hash, exec_summary = report_env
        report = generate_analysis_report(conn, corr, plan, run_hash, exec_summary)
        assert run_hash[:24] in report

    def test_deterministic(self, report_env):
        conn, corr, plan, run_hash, exec_summary = report_env
        r1 = generate_analysis_report(conn, corr, plan, run_hash, exec_summary)
        r2 = generate_analysis_report(conn, corr, plan, run_hash, exec_summary)
        assert r1 == r2
