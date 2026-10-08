#!/usr/bin/env python3
"""DIAGNOSTIC ONLY — NOT CLAIM-SUPPORTING.

This script preserves one legacy candidate hypothesis for the camera-ready
Table IV entropy value of 0.64 nats / 76% reduction. The hardened ARF-RT
fork replay now preserves non-uniform fixture priors and produces
~1.0922 nats / ~59.6% reduction on the §VII-G fixture under its native entropy
computation (full Top-K of 15 paths).

The 0.64 / 76% rounded value can be approximated by post-hoc truncation of
the Top-K to 11 paths, which corresponds to the 11 paths the paper notes
"drop below the viability threshold" after the SCP DENY probe. However, the
exact pre-camera-ready engine convention that produced 0.64 is not preserved
in any archived release. We do not present this script's output as
reproduction evidence; it is retained only to document the discrepancy
between the rounded paper value and the current engine's native output.

Recovered observable values:
  * baseline entropy over 15 paths: ~2.7008
  * top SCP probe EIG after fork-replay hardening: ~1.0724
  * current hardened full engine (all 15 paths): ~1.0922 / ~59.6%
  * older uniform-prior compatibility explorations could approximate 0.64 / 76%
    by combining a buggy fork reset with post-hoc truncation. That is not
    current engine behavior and is not claim-supporting.

Both values are emitted so the artifact does not hide the lineage mismatch.

For v1.2 reproduction claims, see scripts/reproduce_paper.py and the
README's Reconciliation section.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arf_rt.config import Q8  # noqa: E402
from arf_rt.cli import run_full_pipeline  # noqa: E402
from arf_rt.engine.correlation import compute_correlation  # noqa: E402
from arf_rt.engine.paths import search_and_store_top_k  # noqa: E402
from arf_rt.engine.planner import _get_entropy, _get_topk_paths, plan_probes  # noqa: E402
from arf_rt.engine.updater import apply_all_observations  # noqa: E402
from arf_rt.engine.constraints import validate_all_constraints  # noqa: E402
from arf_rt.engine.whatif import fork_db  # noqa: E402


def entropy_from_weights(weights: list[int], include_null: bool = True) -> float:
    all_weights = list(weights)
    if include_null:
        all_weights.append(max(Q8 - sum(weights), 0))
    total = sum(all_weights)
    if total <= 0:
        return 0.0
    return -sum((w / total) * math.log(w / total) for w in all_weights if w > 0)


def _edge_name(conn, edge_id: str) -> str:
    row = conn.execute(
        """SELECT n1.display_name AS src, n2.display_name AS dst
           FROM edges e
           JOIN nodes n1 ON n1.node_id = e.src_node_id
           JOIN nodes n2 ON n2.node_id = e.dst_node_id
           WHERE e.edge_id = ?""",
        (edge_id,),
    ).fetchone()
    if not row:
        return edge_id
    return f"{row['src']} -> {row['dst']}"


def reconstruct(scenario_path: str | Path, planner_signal_q: int = 95, deny_signal_q: int = 96, truncate_after_paths: int = 11) -> dict[str, Any]:
    conn, _ = run_full_pipeline(str(scenario_path))
    corr = compute_correlation(conn)
    plan = plan_probes(conn, corr, signal_q=planner_signal_q)
    top = plan["top_recommendation"]
    edge_id = top["edge_id"]
    baseline_paths = _get_topk_paths(conn)
    baseline_entropy = _get_entropy(conn)

    fork = fork_db(conn)
    fork.execute(
        """INSERT INTO observations
           (edge_id, probe_type, result, reason_class, strength, signal_q,
            is_counterfactual, constraint_relevant, evidence_hash, observed_at)
           VALUES (?, 'REPLAY_SCRIPTED', 'DENY', 'CONSTRAINT_DENY', 'DIRECT', ?, 0, 0, NULL, NULL)""",
        (edge_id, deny_signal_q),
    )
    fork.execute("UPDATE edges SET alpha_i = 1, beta_i = 1, status = 'HYPOTHESIZED', frozen = 0")
    fork.execute("DELETE FROM edge_updates")
    fork.execute("DELETE FROM derived_topk")
    apply_all_observations(fork)
    validate_all_constraints(fork)
    fork.commit()
    search_and_store_top_k(fork, compute_correlation(fork))

    after_paths = _get_topk_paths(fork)
    after_weights = [int(p["p_worst_q8"]) for p in after_paths]
    full_after_entropy = entropy_from_weights(after_weights)
    truncated_weights = after_weights[:truncate_after_paths]
    truncated_after_entropy = entropy_from_weights(truncated_weights)
    probed = fork.execute("SELECT alpha_i, beta_i FROM edges WHERE edge_id = ?", (edge_id,)).fetchone()

    path_probs = [w / Q8 for w in after_weights]
    return {
        "artifact_source": str(scenario_path),
        "probe_edge_id": edge_id,
        "probe_edge_name": _edge_name(conn, edge_id),
        "planner_signal_q": planner_signal_q,
        "deny_signal_q": deny_signal_q,
        "baseline": {
            "entropy": baseline_entropy,
            "paths": len(baseline_paths),
            "top_eig": float(top["eig"]),
            "top_component": plan.get("component_summary", [None])[0],
        },
        "after_deny_full_current_engine": {
            "entropy": full_after_entropy,
            "reduction_pct": 100.0 * (baseline_entropy - full_after_entropy) / baseline_entropy,
            "paths": len(after_paths),
            "viable_paths_gt_1pct": sum(p > 0.01 for p in path_probs),
            "path_probabilities": path_probs,
        },
        "after_deny_table_iv_reconstruction": {
            "entropy": truncated_after_entropy,
            "reduction_pct": 100.0 * (baseline_entropy - truncated_after_entropy) / baseline_entropy,
            "paths_used_for_entropy": len(truncated_weights),
            "reason": "Legacy diagnostic only. Older uniform-prior fork reset plus path truncation could approximate the rounded camera-ready 0.64/76% value; hardened fork replay should not use this as claim evidence.",
        },
        "probed_edge_after_deny": {"alpha": int(probed["alpha_i"]), "beta": int(probed["beta_i"])},
        "lineage_note": "The hardened current full Top-K run preserves non-uniform fixture priors and differs from the camera-ready 0.64/76% text. Do not claim the engine emits 0.64 unless explicitly describing this legacy diagnostic calculation.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", nargs="?", default=str(ROOT / "tests/fixtures/complex_scenario.json"))
    parser.add_argument("--planner-signal-q", type=int, default=95)
    parser.add_argument("--deny-signal-q", type=int, default=96)
    parser.add_argument("--truncate-after-paths", type=int, default=11)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = reconstruct(args.scenario, planner_signal_q=args.planner_signal_q, deny_signal_q=args.deny_signal_q, truncate_after_paths=args.truncate_after_paths)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
