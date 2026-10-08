"""ARF-RT command-line interface.

Usage:
    python -m arf_rt analyze <scenario.json> [--output-dir DIR] [--format md|json|both]
    python -m arf_rt whatif <scenario.json> --refute EDGE_ID [--refute EDGE_ID ...] [--output-dir DIR]
    python -m arf_rt export <scenario.json> [--output FILE]
    python -m arf_rt hash <scenario.json>
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

from arf_rt.adapters.replay import ReplayAdapter
from arf_rt.adapters.seed_json import load_scenario_file
from arf_rt.engine.constraints import validate_all_constraints
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.paths import search_and_store_top_k
from arf_rt.engine.snapshot import canonical_run_hash, full_state_export
from arf_rt.engine.updater import apply_all_observations
from arf_rt.engine.whatif import run_whatif
from arf_rt.reporting.json_output import generate_json_output
from arf_rt.reporting.markdown_report import generate_markdown_report
from arf_rt.storage.sqlite_store import connect

logger = logging.getLogger(__name__)
from arf_rt.util.canon import canonical_json


def run_full_pipeline(scenario_path: str, as_of: str | None = None) -> tuple:
    """Run the full analysis pipeline. Returns (conn, warnings).

    Args:
        scenario_path: Path to scenario JSON file.
        as_of: ISO 8601 reference timestamp for belief decay. If None, no decay.
    """
    conn = connect(":memory:")
    scenario = load_scenario_file(Path(scenario_path))
    adapter = ReplayAdapter(conn)
    ingest_warnings = adapter.ingest(scenario)
    apply_all_observations(conn, as_of=as_of)
    validate_all_constraints(conn)
    conn.commit()
    corr = compute_correlation(conn)
    search_and_store_top_k(conn, corr)
    return conn, ingest_warnings


def cmd_analyze(args: argparse.Namespace) -> int:
    """Run analysis and produce reports."""
    conn, warnings = run_full_pipeline(args.scenario, as_of=getattr(args, "as_of", None))

    output_dir = Path(args.output_dir) if args.output_dir else None
    fmt = args.format

    if fmt in ("md", "both"):
        md = generate_markdown_report(conn)
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "report.md").write_text(md, encoding="utf-8")
            print(f"Markdown report: {output_dir / 'report.md'}")
        else:
            print(md)

    if fmt in ("json", "both"):
        output = generate_json_output(conn)
        text = json.dumps(output, indent=2, sort_keys=True)
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "report.json").write_text(text, encoding="utf-8")
            print(f"JSON report: {output_dir / 'report.json'}")
        else:
            print(text)

    h = canonical_run_hash(conn)
    print(f"canonical_run_hash: {h}", file=sys.stderr)

    return 0


def cmd_whatif(args: argparse.Namespace) -> int:
    """Run what-if analysis."""
    conn, _ = run_full_pipeline(args.scenario)

    result = run_whatif(conn, args.refute, signal_q=args.signal_q)

    output = {
        "baseline_hash": result["baseline_hash"],
        "fork_hash": result["fork_hash"],
        "baseline_verified": result["baseline_verified"],
        "refute_count": len(result["refute_results"]),
        "diff_report": result["diff_report"],
    }

    text = json.dumps(output, indent=2, sort_keys=True)

    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "whatif.json").write_text(text, encoding="utf-8")
        print(f"What-if report: {out / 'whatif.json'}")
    else:
        print(text)

    print(result["diff_report"]["control_roi_line"], file=sys.stderr)

    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export full state as JSON."""
    conn, _ = run_full_pipeline(args.scenario)
    export = full_state_export(conn)
    text = json.dumps(export, indent=2, sort_keys=True)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"State export: {args.output}", file=sys.stderr)
    else:
        print(text)

    return 0


def cmd_hash(args: argparse.Namespace) -> int:
    """Print canonical_run_hash only."""
    conn, _ = run_full_pipeline(args.scenario)
    print(canonical_run_hash(conn))
    return 0


def _load_truth_map(path: str | None) -> dict[str, str] | None:
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "truth_map" in data:
        data = data["truth_map"]
    if not isinstance(data, dict):
        raise ValueError("truth map must be a JSON object of edge_id -> ALLOW/DENY")
    return {str(k): str(v).upper() for k, v in data.items()}


def cmd_eval(args: argparse.Namespace) -> int:
    """Run multi-policy probe-selection evaluation."""
    from arf_rt.engine.eval import format_eval_report, run_evaluation

    policies = [p.strip() for p in args.policies.split(",") if p.strip()]
    truth_map = _load_truth_map(args.truth_map)
    conn, _ = run_full_pipeline(args.scenario, as_of=getattr(args, "as_of", None))
    result = run_evaluation(
        conn, policies=policies, num_episodes=args.episodes, num_steps=args.steps,
        base_seed=args.seed, truth_mode=args.truth_mode, truth_map=truth_map,
        signal_q=args.signal_q, as_of=getattr(args, "as_of", None),
    )
    report = format_eval_report(result, conn, num_steps=args.steps)
    summary = {
        "policies": policies, "episodes": args.episodes, "steps": args.steps,
        "seed": args.seed, "truth_mode": args.truth_mode,
        "median_cumrig": {policy: {str(t): result.median_cum_rig(policy, t) for t in range(1, args.steps + 1)} for policy in policies},
        "canonical_run_hash": canonical_run_hash(conn),
    }
    if args.output_dir:
        out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
        (out / "eval_report.md").write_text(report, encoding="utf-8")
        (out / "eval_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Evaluation report: {out / 'eval_report.md'}")
    elif args.format == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif args.format == "both":
        print(report); print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(report)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """Run probe planner to recommend next edge to test."""
    from arf_rt.engine.planner import plan_probes

    conn, _ = run_full_pipeline(args.scenario, as_of=getattr(args, "as_of", None))
    corr = compute_correlation(conn)
    result = plan_probes(conn, corr, signal_q=args.signal_q, as_of=getattr(args, "as_of", None))

    output = {
        "baseline_entropy": result["baseline_entropy"],
        "top_recommendation": result["top_recommendation"],
        "candidates": [
            {
                "edge_id": c["edge_id"],
                "eig": round(c["eig"], 6),
                "p_edge": round(c["p_edge"], 4),
                "reasons": c["reasons"],
            }
            for c in result["candidates"]
        ],
        "component_summary": result["component_summary"],
        "stats": result["stats"],
    }

    text = json.dumps(output, indent=2, default=str)

    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "plan.json").write_text(text, encoding="utf-8")
        print(f"Plan report: {out / 'plan.json'}")
    else:
        print(text)

    if result["top_recommendation"]:
        top = result["top_recommendation"]
        reasons = ", ".join(top["reasons"])
        stats = result["stats"]
        print(f"Recommendation: probe {top['edge_id'][:16]}... (EIG={top['eig']:.4f}, {reasons})",
              file=sys.stderr)
        print(f"Stats: {stats['total_edges']} edges, {stats['candidate_edges']} candidates, "
              f"{stats['forks_executed']} forks, {stats['runtime_ms']:.0f}ms",
              file=sys.stderr)

    return 0


def cmd_episode(args: argparse.Namespace) -> int:
    """Run a realized-gain episode on a specific edge."""
    from arf_rt.engine.episode import run_episode, format_episode_report

    conn, _ = run_full_pipeline(args.scenario, as_of=getattr(args, "as_of", None))

    # Resolve edge_id: either full hash or prefix
    if len(args.edge) < 64:
        row = conn.execute(
            "SELECT edge_id FROM edges WHERE edge_id LIKE ?",
            (args.edge + "%",),
        ).fetchone()
        if not row:
            print(f"No edge matching prefix: {args.edge}", file=sys.stderr)
            return 1
        edge_id = row["edge_id"]
    else:
        edge_id = args.edge

    ep = run_episode(
        conn, edge_id, args.outcome.upper(),
        signal_q=args.signal_q,
        as_of=getattr(args, "as_of", None),
    )

    report = format_episode_report(ep, conn)

    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"episode_{args.outcome.lower()}.md").write_text(report, encoding="utf-8")
        ep_json = json.dumps(ep, indent=2, default=str)
        (out / f"episode_{args.outcome.lower()}.json").write_text(ep_json, encoding="utf-8")
        print(f"Episode report: {out / f'episode_{args.outcome.lower()}.md'}")
    else:
        print(report)

    # Persist updated scenario with the new observation
    save_path = getattr(args, "save", None)
    if save_path:
        _save_post_episode_scenario(args.scenario, ep, save_path, conn)
        print(f"Updated scenario saved to {save_path}", file=sys.stderr)

    rig_sign = "+" if ep["rig"] >= 0 else ""
    print(
        f"RIG={rig_sign}{ep['rig']:.4f}  EIG={ep['eig']:.4f}  "
        f"H: {ep['h_before']:.4f}→{ep['h_after']:.4f}  "
        f"pred_err={ep['prediction_error']:.4f}",
        file=sys.stderr,
    )

    return 0


def _save_post_episode_scenario(
    original_path: str, episode: dict, save_path: str,
    conn: sqlite3.Connection,
) -> None:
    """Save a copy of the scenario with the episode observation appended."""
    with open(original_path) as f:
        scenario = json.load(f)

    edge_id = episode["edge_id"]

    # Reconstruct edge_ref from the DB
    edge_row = conn.execute(
        """SELECT e.edge_type, n1.provider_id as src_pid, n2.provider_id as dst_pid,
                  n1.provider as src_prov, n1.node_type as src_type, n1.region as src_region,
                  n2.provider as dst_prov, n2.node_type as dst_type, n2.region as dst_region,
                  e.region
           FROM edges e
           JOIN nodes n1 ON n1.node_id = e.src_node_id
           JOIN nodes n2 ON n2.node_id = e.dst_node_id
           WHERE e.edge_id = ?""",
        (edge_id,),
    ).fetchone()

    if edge_row:
        new_obs = {
            "edge_ref": {
                "edge_type": edge_row["edge_type"],
                "src": {"provider": edge_row["src_prov"], "node_type": edge_row["src_type"],
                        "provider_id": edge_row["src_pid"], "region": edge_row["src_region"]},
                "dst": {"provider": edge_row["dst_prov"], "node_type": edge_row["dst_type"],
                        "provider_id": edge_row["dst_pid"], "region": edge_row["dst_region"]},
                "region": edge_row["region"],
            },
            "probe_type": "REPLAY_SCRIPTED",
            "result": episode["outcome"],
            "reason_class": "UNKNOWN",
            "strength": "DIRECT",
            "signal_q": 95,
            "is_counterfactual": False,
            "constraint_relevant": episode["outcome"] == "DENY",
            "evidence_hash": f"episode-{edge_id[:16]}",
        }
    else:
        logger.warning("Edge %s not found in DB, using edge_id reference", edge_id)
        new_obs = {
            "edge_ref": {"edge_id": edge_id},
            "probe_type": "REPLAY_SCRIPTED",
            "result": episode["outcome"],
            "reason_class": "UNKNOWN",
            "strength": "DIRECT",
            "signal_q": 95,
            "is_counterfactual": False,
            "constraint_relevant": episode["outcome"] == "DENY",
            "evidence_hash": f"episode-{edge_id[:16]}",
        }

    if "observations" not in scenario:
        scenario["observations"] = []
    scenario["observations"].append(new_obs)

    with open(save_path, "w") as f:
        json.dump(scenario, f, indent=2, sort_keys=True)


def cmd_import_pmapper(args: argparse.Namespace) -> int:
    """Build scenario JSON from PMapper graph + optional AWS Organizations."""
    from arf_rt.adapters.scenario_builder import build_and_save
    from arf_rt.adapters.pmapper import translate_from_file

    # Build objectives from --start/--target if provided
    objectives = None
    objectives_path = getattr(args, "objectives", None)

    if args.start and args.target:
        translated = translate_from_file(args.pmapper)
        start_node = None
        target_node = None
        for n in translated.nodes:
            if n["provider_id"] == args.start:
                start_node = n
            if n["provider_id"] == args.target:
                target_node = n
        if not start_node:
            print(f"Error: start node '{args.start}' not found in PMapper graph", file=sys.stderr)
            return 1
        if not target_node:
            print(f"Error: target node '{args.target}' not found in PMapper graph", file=sys.stderr)
            return 1
        objectives = [{
            "objective_type": "REACHABILITY",
            "start_nodes": [start_node],
            "target_nodes": [target_node],
            "max_depth": args.max_depth,
            "k": args.k,
        }]
    elif not objectives_path:
        print("Warning: no objectives specified (use --start/--target or --objectives)", file=sys.stderr)

    build_and_save(
        args.pmapper,
        args.output,
        org_path=getattr(args, "org", None),
        objectives=objectives,
        objectives_path=objectives_path,
        observations_path=getattr(args, "observations", None),
    )
    print(f"Scenario saved to {args.output}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arf-rt",
        description="ARF-RT: Attachment-Regulation Framework — Risk Topology engine",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # analyze
    p_analyze = sub.add_parser("analyze", help="Run full analysis")
    p_analyze.add_argument("scenario", help="Path to scenario JSON file")
    p_analyze.add_argument("--output-dir", "-o", help="Output directory")
    p_analyze.add_argument("--format", "-f", choices=["md", "json", "both"], default="both")
    p_analyze.add_argument(
        "--as-of", help="ISO 8601 timestamp for belief decay (e.g., 2025-06-01T00:00:00Z)"
    )

    # whatif
    p_whatif = sub.add_parser("whatif", help="Run what-if analysis")
    p_whatif.add_argument("scenario", help="Path to scenario JSON file")
    p_whatif.add_argument("--refute", "-r", action="append", required=True, help="Edge ID to refute")
    p_whatif.add_argument("--signal-q", type=int, default=100, help="Signal quality (default 100)")
    p_whatif.add_argument("--output-dir", "-o", help="Output directory")

    # export
    p_export = sub.add_parser("export", help="Export full state as JSON")
    p_export.add_argument("scenario", help="Path to scenario JSON file")
    p_export.add_argument("--output", "-o", help="Output file path")

    # hash
    p_hash = sub.add_parser("hash", help="Print canonical_run_hash")
    p_hash.add_argument("scenario", help="Path to scenario JSON file")

    # eval
    p_eval = sub.add_parser("eval", help="Run multi-policy probe-selection evaluation")
    p_eval.add_argument("scenario", help="Path to scenario JSON file")
    p_eval.add_argument("--episodes", type=int, default=10, help="Episodes per policy")
    p_eval.add_argument("--steps", type=int, default=5, help="Steps per episode")
    p_eval.add_argument("--seed", type=int, default=1337, help="Base RNG seed")
    p_eval.add_argument("--policies", default="eig,random,uncertainty,centrality", help="Comma-separated policies")
    p_eval.add_argument("--truth-mode", choices=["sampled", "scripted"], default="sampled")
    p_eval.add_argument("--truth-map", help="JSON edge_id -> ALLOW/DENY map for scripted mode")
    p_eval.add_argument("--signal-q", type=int, default=95, help="Signal quality")
    p_eval.add_argument("--as-of", help="ISO 8601 timestamp for belief decay")
    p_eval.add_argument("--output-dir", "-o", help="Output directory")
    p_eval.add_argument("--format", choices=["md", "json", "both"], default="md")

    # plan
    p_plan = sub.add_parser("plan", help="Recommend next edge to probe")
    p_plan.add_argument("scenario", help="Path to scenario JSON file")
    p_plan.add_argument("--output-dir", "-o", help="Output directory")
    p_plan.add_argument("--signal-q", type=int, default=95, help="Signal quality for simulated probes")
    p_plan.add_argument("--as-of", help="ISO 8601 timestamp for belief decay")

    # episode
    p_ep = sub.add_parser("episode", help="Run a realized-gain episode")
    p_ep.add_argument("scenario", help="Path to scenario JSON file")
    p_ep.add_argument("--edge", required=True, help="Edge ID (or prefix) to probe")
    p_ep.add_argument("--outcome", required=True, choices=["allow", "deny", "ALLOW", "DENY"],
                       help="Forced probe outcome")
    p_ep.add_argument("--output-dir", "-o", help="Output directory")
    p_ep.add_argument("--signal-q", type=int, default=100, help="Signal quality for probe")
    p_ep.add_argument("--as-of", help="ISO 8601 timestamp for belief decay")
    p_ep.add_argument("--save", help="Save updated scenario (with observation) to this path")

    # import-pmapper
    p_import = sub.add_parser("import-pmapper", help="Build scenario from PMapper + AWS Organizations")
    p_import.add_argument("pmapper", help="Path to PMapper graph JSON")
    p_import.add_argument("--org", help="Path to AWS Organizations JSON (optional)")
    p_import.add_argument("--objectives", help="Path to objectives JSON file")
    p_import.add_argument("--observations", help="Path to observations JSON file")
    p_import.add_argument("--output", "-o", default="scenario.json", help="Output scenario path (default: scenario.json)")
    p_import.add_argument("--start", help="Start node provider_id (e.g., arn:aws:iam::111:user/attacker)")
    p_import.add_argument("--target", help="Target node provider_id (e.g., arn:aws:iam::222:role/admin)")
    p_import.add_argument("--max-depth", type=int, default=6, help="Max path depth (default: 6)")
    p_import.add_argument("--k", type=int, default=10, help="Top-K paths (default: 10)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "analyze": cmd_analyze,
        "whatif": cmd_whatif,
        "export": cmd_export,
        "hash": cmd_hash,
        "eval": cmd_eval,
        "plan": cmd_plan,
        "episode": cmd_episode,
        "import-pmapper": cmd_import_pmapper,
    }

    try:
        return dispatch[args.command](args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
