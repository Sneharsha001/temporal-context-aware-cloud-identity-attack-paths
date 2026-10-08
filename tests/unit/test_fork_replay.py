"""Hardening tests for fork replay reset semantics."""

from __future__ import annotations

import json
from pathlib import Path

from arf_rt.cli import run_full_pipeline
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.eval import run_evaluation
from arf_rt.engine.planner import _simulate_probe, plan_probes
from tests.golden.test_eval import _build_baseline


FIXTURES = Path(__file__).parent.parent / "fixtures"


def _plan_top_edge(conn):
    corr = compute_correlation(conn)
    plan = plan_probes(conn, corr)
    return corr, plan["top_recommendation"]["edge_id"]


class TestForkReplayBaseState:
    def test_non_uniform_priors_preserved_in_planner_fork(self) -> None:
        conn, _ = run_full_pipeline(str(FIXTURES / "complex_scenario.json"))
        corr, top_edge = _plan_top_edge(conn)

        assert conn.execute(
            """SELECT COUNT(*) FROM observations"""
        ).fetchone()[0] == 0
        non_default = conn.execute(
            """SELECT COUNT(*) FROM edges
               WHERE base_alpha_i != 1 OR base_beta_i != 1"""
        ).fetchone()[0]
        assert non_default > 0

        fork = _simulate_probe(conn, top_edge, "DENY", static_correlation=corr)

        mismatches = fork.execute(
            """SELECT edge_id FROM edges
               WHERE edge_id != ?
                 AND (alpha_i != base_alpha_i OR beta_i != base_beta_i)""",
            (top_edge,),
        ).fetchall()
        assert mismatches == []

    def test_complex_fixture_allow_and_deny_preserve_non_probed_priors(self) -> None:
        conn, _ = run_full_pipeline(str(FIXTURES / "complex_scenario.json"))
        corr, top_edge = _plan_top_edge(conn)

        baseline_non_default = conn.execute(
            """SELECT COUNT(*) FROM edges
               WHERE base_alpha_i != 1 OR base_beta_i != 1"""
        ).fetchone()[0]
        assert baseline_non_default > 10

        for outcome in ("ALLOW", "DENY"):
            fork = _simulate_probe(conn, top_edge, outcome, static_correlation=corr)
            preserved = fork.execute(
                """SELECT COUNT(*) FROM edges
                   WHERE edge_id != ?
                     AND (alpha_i != base_alpha_i OR beta_i != base_beta_i)""",
                (top_edge,),
            ).fetchone()[0]
            assert preserved == 0

    def test_template_replay_does_not_double_count_baseline_observations(self) -> None:
        conn, _ = run_full_pipeline(str(FIXTURES / "primary_realistic_scenario.json"))
        corr, top_edge = _plan_top_edge(conn)

        top_template_id = conn.execute(
            "SELECT template_id FROM edges WHERE edge_id = ?",
            (top_edge,),
        ).fetchone()["template_id"]
        before = {
            r["template_id"]: dict(r)
            for r in conn.execute(
                """SELECT template_id, alpha_agg_i, beta_agg_i, sample_count
                   FROM templates"""
            ).fetchall()
        }

        fork = _simulate_probe(conn, top_edge, "DENY", static_correlation=corr)
        after = {
            r["template_id"]: dict(r)
            for r in fork.execute(
                """SELECT template_id, alpha_agg_i, beta_agg_i, sample_count
                   FROM templates"""
            ).fetchall()
        }

        for template_id, expected in before.items():
            actual = after[template_id]
            if template_id == top_template_id:
                assert actual["alpha_agg_i"] == expected["alpha_agg_i"]
                assert actual["beta_agg_i"] == expected["beta_agg_i"] + 90
                assert actual["sample_count"] == expected["sample_count"] + 1
            else:
                assert actual == expected


class TestForkReplayDeterminism:
    def test_repeated_plan_outputs_identical(self) -> None:
        outputs = []
        for _ in range(3):
            conn, _ = run_full_pipeline(str(FIXTURES / "complex_scenario.json"))
            corr = compute_correlation(conn)
            plan = plan_probes(conn, corr)
            outputs.append(json.dumps({
                "baseline_entropy": plan["baseline_entropy"],
                "top": plan["top_recommendation"],
                "candidates": [
                    (c["edge_id"], c["eig"], c["h_allow"], c["h_deny"], c["p_edge"])
                    for c in plan["candidates"]
                ],
                "components": plan["component_summary"],
            }, sort_keys=True))
        assert len(set(outputs)) == 1

    def test_repeated_eval_outputs_identical(self) -> None:
        conn, truth_map = _build_baseline()
        outputs = []
        for _ in range(3):
            result = run_evaluation(
                conn,
                policies=["eig", "uncertainty", "random"],
                num_episodes=3,
                num_steps=3,
                base_seed=1337,
                truth_mode="scripted",
                truth_map=truth_map,
                signal_q=95,
            )
            outputs.append(json.dumps({
                policy: {
                    str(t): result.median_cum_rig(policy, t)
                    for t in range(1, 4)
                }
                for policy in ["eig", "uncertainty", "random"]
            }, sort_keys=True))
        assert len(set(outputs)) == 1
