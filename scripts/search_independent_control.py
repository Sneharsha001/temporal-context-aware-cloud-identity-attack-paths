#!/usr/bin/env python3
"""Search deterministic truth maps for the independent-control experiment.

This is a diagnostic, not a license to cherry-pick. Use it to characterize
whether any fair deterministic truth map lands near the camera-ready
EIG/uncertainty equality claim. The hardened artifact should still be described
as supporting uncertainty-like behavior, not as exactly reproducing equality.
If a near-equality map is found, record the rule and seed; if not, keep the
paper/talk wording at "EIG advantage shrinks toward the uncertainty baseline."
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.golden.test_independent_fixture import _build_independent_baseline  # noqa: E402
from arf_rt.engine.eval import run_evaluation  # noqa: E402


def edge_rows(conn):
    return conn.execute(
        """
        SELECT e.edge_id, n1.provider_id AS src, n2.provider_id AS dst
        FROM edges e
        JOIN nodes n1 ON n1.node_id=e.src_node_id
        JOIN nodes n2 ON n2.node_id=e.dst_node_id
        ORDER BY e.edge_id
        """
    ).fetchall()


def truth_map_for_seed(rows, seed: int, p_allow: float) -> dict[str, str]:
    rng = random.Random(seed)
    return {r["edge_id"]: ("ALLOW" if rng.random() < p_allow else "DENY") for r in rows}


def truth_map_sha_rule(rows, salt: str) -> dict[str, str]:
    out = {}
    for r in rows:
        src = r["src"].split("/")[-1]
        dst = r["dst"].split("/")[-1]
        digest = hashlib.sha256(f"{salt}:{src}->{dst}".encode("utf-8")).hexdigest()
        out[r["edge_id"]] = "ALLOW" if int(digest[:8], 16) % 2 == 0 else "DENY"
    return out


def evaluate(conn, truth_map, episodes: int, steps: int, signal_q: int) -> dict[str, float]:
    result = run_evaluation(
        conn,
        policies=["eig", "uncertainty", "random"],
        num_episodes=episodes,
        num_steps=steps,
        base_seed=1337,
        truth_mode="scripted",
        truth_map=truth_map,
        signal_q=signal_q,
    )
    eig5 = result.median_cum_rig("eig", steps)
    unc5 = result.median_cum_rig("uncertainty", steps)
    rand5 = result.median_cum_rig("random", steps)
    ratio = eig5 / unc5 if abs(unc5) > 1e-12 else float("inf")
    return {"eig": eig5, "uncertainty": unc5, "random": rand5, "eig_vs_uncertainty": ratio}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-seeds", type=int, default=25)
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--steps", type=int, default=5)
    parser.add_argument("--signal-q", type=int, default=95)
    parser.add_argument("--p-allow", type=float, default=0.5)
    parser.add_argument("--output", default="artifacts/reproduction/independent_control_search.json")
    args = parser.parse_args()

    t0 = time.perf_counter()
    conn = _build_independent_baseline()
    rows = edge_rows(conn)
    best: list[dict[str, object]] = []

    # Include the current deterministic SHA rule first.
    candidates: list[tuple[str, dict[str, str]]] = [("sha256_current", truth_map_sha_rule(rows, "current"))]
    for seed in range(args.max_seeds):
        candidates.append((f"random_seed_{seed}", truth_map_for_seed(rows, seed, args.p_allow)))

    for name, tm in candidates:
        metrics = evaluate(conn, tm, args.episodes, args.steps, args.signal_q)
        ratio = float(metrics["eig_vs_uncertainty"])
        distance = abs(ratio - 1.0) if ratio != float("inf") else 1e9
        item = {"name": name, "distance_from_1x": distance, **metrics, "truth_map": tm}
        best.append(item)
        best.sort(key=lambda x: float(x["distance_from_1x"]))
        best = best[:10]

    result = {
        "note": "Diagnostic search only. Do not cherry-pick without documenting the rule/seed before using the claim.",
        "episodes": args.episodes,
        "steps": args.steps,
        "signal_q": args.signal_q,
        "p_allow": args.p_allow,
        "elapsed_s": time.perf_counter() - t0,
        "best": best,
    }
    out = Path(args.output)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(out)
    print(json.dumps({k: v for k, v in best[0].items() if k != "truth_map"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
