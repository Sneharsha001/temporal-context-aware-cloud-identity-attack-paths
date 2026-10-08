"""Multi-policy evaluation framework for probe selection.

Compares three probe selection policies over sequential episodes:
    - eig: choose edge with highest Expected Information Gain
    - random: uniform random over candidates
    - uncertainty: choose edge with P(allow) closest to 0.5

Each episode runs N sequential steps from a frozen baseline. Within an
episode, observations accumulate (sequential learning). Across episodes,
different RNG seeds produce different outcome sequences.

Truth mode:
    - scripted: deterministic truth map (edge_id → ALLOW/DENY)
    - sampled: draw outcome from Bernoulli(p_allow) with fixed seed
"""

from __future__ import annotations

import json
import math
import random
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from arf_rt.engine.constraints import validate_all_constraints
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.paths import search_and_store_top_k
from arf_rt.engine.planner import (
    _get_entropy,
    _get_topk_paths,
    plan_probes,
)
from arf_rt.engine.updater import apply_all_observations, reset_replay_state
from arf_rt.engine.whatif import fork_db


# ===================================================================
# Data structures
# ===================================================================


@dataclass
class StepResult:
    """Result of a single probe step within an episode."""

    step: int
    edge_id: str
    eig: float
    p_allow: float
    outcome: str
    h_before: float
    h_after: float
    rig: float
    cum_rig: float
    is_representative: bool
    rep_before: str | None
    rep_after: str | None
    rep_flipped: bool
    paths_before: int
    paths_after: int


@dataclass
class EpisodeResult:
    """Result of a complete multi-step episode."""

    policy: str
    seed: int
    steps: list[StepResult] = field(default_factory=list)

    @property
    def cum_rig_at(self) -> dict[int, float]:
        """Cumulative RIG at each step T."""
        return {s.step: s.cum_rig for s in self.steps}

    @property
    def final_cum_rig(self) -> float:
        return self.steps[-1].cum_rig if self.steps else 0.0


@dataclass
class EvalResult:
    """Result of a full evaluation across policies."""

    policies: dict[str, list[EpisodeResult]] = field(default_factory=dict)

    def median_cum_rig(self, policy: str, at_step: int) -> float:
        """Median cumulative RIG at step T for a policy."""
        vals = []
        for ep in self.policies.get(policy, []):
            for s in ep.steps:
                if s.step == at_step:
                    vals.append(s.cum_rig)
                    break
        if not vals:
            return 0.0
        vals.sort()
        n = len(vals)
        if n % 2 == 1:
            return vals[n // 2]
        return (vals[n // 2 - 1] + vals[n // 2]) / 2

    def mean_cum_rig(self, policy: str, at_step: int) -> float:
        vals = []
        for ep in self.policies.get(policy, []):
            for s in ep.steps:
                if s.step == at_step:
                    vals.append(s.cum_rig)
                    break
        return sum(vals) / len(vals) if vals else 0.0

    def rep_vs_nonrep_rig(self, policy: str) -> tuple[float, float]:
        """Average RIG when probing rep vs non-rep edges."""
        rep_rigs = []
        nonrep_rigs = []
        for ep in self.policies.get(policy, []):
            for s in ep.steps:
                if s.is_representative:
                    rep_rigs.append(s.rig)
                else:
                    nonrep_rigs.append(s.rig)
        avg_rep = sum(rep_rigs) / len(rep_rigs) if rep_rigs else 0.0
        avg_nonrep = sum(nonrep_rigs) / len(nonrep_rigs) if nonrep_rigs else 0.0
        return avg_rep, avg_nonrep

    def flip_rate(self, policy: str) -> float:
        """Fraction of steps where rep flipped."""
        total = 0
        flips = 0
        for ep in self.policies.get(policy, []):
            for s in ep.steps:
                total += 1
                if s.rep_flipped:
                    flips += 1
        return flips / total if total > 0 else 0.0


# ===================================================================
# Policy selection
# ===================================================================


def choose_candidate(
    policy: str,
    candidates: list[dict],
    rng: random.Random,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Select a candidate edge based on policy.

    Args:
        policy: "eig", "random", "uncertainty", or "centrality".
        candidates: List of candidate dicts from plan_probes().
        rng: Seeded RNG for reproducibility.
        conn: DB connection (required for centrality policy).

    Returns:
        The selected candidate dict.
    """
    if not candidates:
        raise ValueError("No candidates to choose from")

    if policy == "eig":
        return max(candidates, key=lambda c: c["eig"])
    elif policy == "random":
        return rng.choice(candidates)
    elif policy == "uncertainty":
        # Edge closest to p=0.5, with random tiebreaking
        # This is a naive baseline — it only sees local uncertainty, not correlation
        min_dist = min(abs(c["p_edge"] - 0.5) for c in candidates)
        ties = [c for c in candidates if abs(abs(c["p_edge"] - 0.5) - min_dist) < 1e-9]
        return rng.choice(ties)
    elif policy == "centrality":
        # Edge appearing on the most Top-K paths
        if conn is None:
            raise ValueError("centrality policy requires conn")
        path_counts: dict[str, int] = {}
        rows = conn.execute("SELECT edge_id_sequence FROM derived_topk").fetchall()
        for row in rows:
            for eid in json.loads(row["edge_id_sequence"]):
                path_counts[eid] = path_counts.get(eid, 0) + 1
        return max(candidates, key=lambda c: path_counts.get(c["edge_id"], 0))
    else:
        raise ValueError(f"Unknown policy: {policy}")


# ===================================================================
# Outcome determination
# ===================================================================


def determine_outcome(
    edge_id: str,
    p_allow: float,
    truth_mode: str,
    truth_map: dict[str, str] | None,
    rng: random.Random,
) -> str:
    """Determine the probe outcome.

    Args:
        edge_id: Edge being probed.
        p_allow: Current P(allow) for the edge.
        truth_mode: "scripted" or "sampled".
        truth_map: edge_id → "ALLOW"/"DENY" (for scripted mode).
        rng: Seeded RNG.

    Returns:
        "ALLOW" or "DENY".
    """
    if truth_mode == "scripted":
        if not truth_map or edge_id not in truth_map:
            raise ValueError(f"No scripted truth for edge {edge_id}")
        return truth_map[edge_id]
    elif truth_mode == "sampled":
        return "ALLOW" if rng.random() < p_allow else "DENY"
    else:
        raise ValueError(f"Unknown truth_mode: {truth_mode}")


# ===================================================================
# Episode runner
# ===================================================================


def run_eval_episode(
    baseline_conn: sqlite3.Connection,
    policy: str,
    num_steps: int,
    seed: int,
    truth_mode: str = "sampled",
    truth_map: dict[str, str] | None = None,
    signal_q: int = 95,
    as_of: str | None = None,
) -> EpisodeResult:
    """Run a single evaluation episode.

    Starts from a fork of the baseline and applies sequential probes.

    Args:
        baseline_conn: Frozen baseline pipeline DB.
        policy: "eig", "random", or "uncertainty".
        num_steps: Number of sequential probe steps.
        seed: RNG seed for reproducibility.
        truth_mode: "scripted" or "sampled".
        truth_map: Edge truth map for scripted mode.
        signal_q: Signal quality for probe observations.
        as_of: Reference timestamp.

    Returns:
        EpisodeResult with per-step telemetry.
    """
    rng = random.Random(seed)
    result = EpisodeResult(policy=policy, seed=seed)

    # Fork from baseline — this is the evolving state
    working = fork_db(baseline_conn)
    cum_rig = 0.0

    for step in range(1, num_steps + 1):
        # Compute current state
        corr = compute_correlation(working)
        h_before = _get_entropy(working)
        paths_before = len(_get_topk_paths(working))

        # Run planner
        plan = plan_probes(working, corr, signal_q=signal_q, as_of=as_of)
        candidates = plan.get("candidates", [])

        if not candidates:
            break

        # Select edge
        chosen = choose_candidate(policy, candidates, rng, conn=working)
        edge_id = chosen["edge_id"]
        eig = chosen["eig"]
        p_edge = chosen["p_edge"]

        # Check if representative
        edge_groups = corr.get("edge_groups", {})
        p_worst_reps = corr.get("p_worst_reps", {})
        rep_before = None
        is_rep = False
        if edge_id in edge_groups:
            sig = edge_groups[edge_id].get("p_worst_sig")
            if sig:
                rep_before = p_worst_reps.get(sig)
                is_rep = (rep_before == edge_id)

        # Determine outcome
        outcome = determine_outcome(edge_id, p_edge, truth_mode, truth_map, rng)

        # Apply observation to working DB
        working.execute(
            """INSERT INTO observations
               (edge_id, probe_type, result, reason_class, strength,
                signal_q, is_counterfactual, constraint_relevant,
                evidence_hash, observed_at)
               VALUES (?, 'REPLAY_SCRIPTED', ?, ?, 'DIRECT', ?, 0, 0, NULL, ?)""",
            (
                edge_id,
                outcome,
                "UNKNOWN" if outcome == "ALLOW" else "CONSTRAINT_DENY",
                signal_q,
                as_of,
            ),
        )

        # Restore mutable replay state to ingested priors and rerun pipeline.
        reset_replay_state(working)

        apply_all_observations(working, as_of=as_of)
        validate_all_constraints(working)
        working.commit()

        corr_after = compute_correlation(working)
        search_and_store_top_k(working, corr_after)

        # Measure
        h_after = _get_entropy(working)
        paths_after = len(_get_topk_paths(working))
        rig = h_before - h_after
        cum_rig += rig

        # Check rep after
        rep_after = None
        if edge_id in corr_after.get("edge_groups", {}):
            sig = corr_after["edge_groups"][edge_id].get("p_worst_sig")
            if sig:
                rep_after = corr_after.get("p_worst_reps", {}).get(sig)

        result.steps.append(StepResult(
            step=step,
            edge_id=edge_id,
            eig=eig,
            p_allow=p_edge,
            outcome=outcome,
            h_before=h_before,
            h_after=h_after,
            rig=rig,
            cum_rig=cum_rig,
            is_representative=is_rep,
            rep_before=rep_before,
            rep_after=rep_after,
            rep_flipped=(rep_before is not None and rep_before != rep_after),
            paths_before=paths_before,
            paths_after=paths_after,
        ))

    return result


# ===================================================================
# Full evaluation
# ===================================================================


def run_evaluation(
    baseline_conn: sqlite3.Connection,
    policies: list[str] | None = None,
    num_episodes: int = 10,
    num_steps: int = 5,
    base_seed: int = 1337,
    truth_mode: str = "sampled",
    truth_map: dict[str, str] | None = None,
    signal_q: int = 95,
    as_of: str | None = None,
) -> EvalResult:
    """Run full policy comparison evaluation.

    Each policy runs the same set of episodes (same seeds).

    Args:
        baseline_conn: Frozen baseline pipeline DB.
        policies: Policies to compare. Default: ["eig", "random", "uncertainty"].
        num_episodes: Number of episodes per policy.
        num_steps: Steps per episode.
        base_seed: Starting seed (episode i uses base_seed + i).
        truth_mode: "scripted" or "sampled".
        truth_map: Edge truth map for scripted mode.
        signal_q: Signal quality.
        as_of: Reference timestamp.

    Returns:
        EvalResult with all episodes for all policies.
    """
    if policies is None:
        policies = ["eig", "random", "uncertainty"]

    eval_result = EvalResult()

    for policy in policies:
        episodes = []
        for i in range(num_episodes):
            seed = base_seed + i
            ep = run_eval_episode(
                baseline_conn, policy, num_steps, seed,
                truth_mode, truth_map, signal_q, as_of,
            )
            episodes.append(ep)
        eval_result.policies[policy] = episodes

    return eval_result


# ===================================================================
# Report formatting
# ===================================================================


def format_eval_report(
    eval_result: EvalResult,
    conn: sqlite3.Connection,
    num_steps: int = 5,
) -> str:
    """Format evaluation results as Markdown."""
    from arf_rt.reporting.analysis_report import edge_name

    md = []
    md.append("# ARF-RT Policy Evaluation Report")
    md.append("")

    policies = list(eval_result.policies.keys())
    n_episodes = len(next(iter(eval_result.policies.values()), []))
    n_steps = num_steps

    md.append(f"**Policies**: {', '.join(policies)}")
    md.append(f"**Episodes per policy**: {n_episodes}")
    md.append(f"**Steps per episode**: {n_steps}")
    md.append("")

    # Cumulative RIG table
    md.append("## Cumulative RIG by Policy")
    md.append("")
    steps_to_show = [t for t in [1, 2, 3, 5] if t <= n_steps]
    header = "| Policy | " + " | ".join(f"Median CumRIG@{t}" for t in steps_to_show) + " |"
    sep = "|--------|" + "|".join("-------:" for _ in steps_to_show) + "|"
    md.append(header)
    md.append(sep)
    for policy in policies:
        vals = [f"{eval_result.median_cum_rig(policy, t):.4f}" for t in steps_to_show]
        md.append(f"| {policy} | " + " | ".join(vals) + " |")
    md.append("")

    # Mean CumRIG table
    md.append("## Mean CumRIG by Policy")
    md.append("")
    header = "| Policy | " + " | ".join(f"Mean CumRIG@{t}" for t in steps_to_show) + " |"
    md.append(header)
    md.append(sep)
    for policy in policies:
        vals = [f"{eval_result.mean_cum_rig(policy, t):.4f}" for t in steps_to_show]
        md.append(f"| {policy} | " + " | ".join(vals) + " |")
    md.append("")

    # Check for mean/median divergence on random
    if "random" in policies:
        max_step = max(steps_to_show)
        rand_med = eval_result.median_cum_rig("random", max_step)
        rand_mean = eval_result.mean_cum_rig("random", max_step)
        if rand_mean > 0 and rand_med > 0 and rand_mean / rand_med > 2.0:
            md.append(f"*Note: Random policy shows mean/median divergence at step {max_step} "
                      f"(mean={rand_mean:.4f}, median={rand_med:.4f}). "
                      f"A few lucky episodes pulled the mean up. "
                      f"Medians are the correct summary for skewed distributions.*")
            md.append("")

    # Ratio vs random
    if "random" in policies and "eig" in policies:
        md.append("## EIG Advantage")
        md.append("")
        for t in steps_to_show:
            eig_med = eval_result.median_cum_rig("eig", t)
            rand_med = eval_result.median_cum_rig("random", t)
            if rand_med > 0:
                ratio = eig_med / rand_med
                md.append(f"- **CumRIG@{t}**: EIG median = {eig_med:.4f}, Random median = {rand_med:.4f} (ratio {ratio:.2f}×)")
            elif eig_med > 0:
                md.append(f"- **CumRIG@{t}**: EIG median = {eig_med:.4f}, Random median = {rand_med:.4f} (EIG wins, random at zero)")
            else:
                md.append(f"- **CumRIG@{t}**: EIG median = {eig_med:.4f}, Random median = {rand_med:.4f}")
        md.append("")

    if "uncertainty" in policies and "eig" in policies:
        for t in steps_to_show:
            eig_med = eval_result.median_cum_rig("eig", t)
            unc_med = eval_result.median_cum_rig("uncertainty", t)
            if unc_med > 0:
                ratio = eig_med / unc_med
                md.append(f"- **CumRIG@{t}**: EIG median = {eig_med:.4f}, Uncertainty median = {unc_med:.4f} (ratio {ratio:.2f}×)")
            elif eig_med > 0:
                md.append(f"- **CumRIG@{t}**: EIG median = {eig_med:.4f}, Uncertainty median = {unc_med:.4f} (EIG wins)")
            else:
                md.append(f"- **CumRIG@{t}**: EIG median = {eig_med:.4f}, Uncertainty median = {unc_med:.4f}")
        md.append("")

    if "centrality" in policies and "eig" in policies:
        md.append("### EIG vs Centrality")
        md.append("")
        for t in steps_to_show:
            eig_med = eval_result.median_cum_rig("eig", t)
            cent_med = eval_result.median_cum_rig("centrality", t)
            if cent_med > 0:
                ratio = eig_med / cent_med
                md.append(f"- **CumRIG@{t}**: EIG median = {eig_med:.4f}, Centrality median = {cent_med:.4f} (ratio {ratio:.2f}×)")
            elif eig_med > 0:
                md.append(f"- **CumRIG@{t}**: EIG median = {eig_med:.4f}, Centrality median = {cent_med:.4f} (EIG wins)")
            else:
                md.append(f"- **CumRIG@{t}**: EIG median = {eig_med:.4f}, Centrality median = {cent_med:.4f}")
        md.append("")

    # Correlation readout (EIG policy only)
    if "eig" in policies:
        md.append("## Correlation Leverage (EIG policy)")
        md.append("")
        avg_rep, avg_nonrep = eval_result.rep_vs_nonrep_rig("eig")
        flip = eval_result.flip_rate("eig")
        md.append(f"- Avg RIG when probing representative: {avg_rep:.4f}")
        md.append(f"- Avg RIG when probing non-representative: {avg_nonrep:.4f}")
        if avg_nonrep != 0:
            md.append(f"- Rep leverage ratio: {avg_rep / avg_nonrep:.2f}×")
        md.append(f"- Rep flip rate: {flip:.1%}")
        md.append("")

    return "\n".join(md)
