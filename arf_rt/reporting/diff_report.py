"""Diff report for what-if comparison (spec §17.3).

Compares baseline and fork state exports to produce a diff report.
This is a stub — full implementation in Session 9 (What-If).

Control ROI line format (spec §17.3):
  Control ROI: X of Top-K paths removed (Y%), highest remaining path
  confidence: <High|Medium|Low>, evidence coverage: Z% of edges observed.
"""

from __future__ import annotations

from typing import Any


def generate_diff_report(
    baseline_export: dict[str, Any],
    fork_export: dict[str, Any],
) -> dict[str, Any]:
    """Compare baseline and fork state exports.

    Args:
        baseline_export: Output of full_state_export() on baseline DB.
        fork_export: Output of full_state_export() on fork DB.

    Returns:
        Diff report dict with:
          - paths_removed: count of baseline paths not in fork
          - paths_remaining: count of paths still present
          - highest_remaining_band: confidence band of best remaining path
          - evidence_coverage_pct: from fork
          - control_roi_line: formatted string per spec §17.3
          - edge_diffs: list of edges with changed beliefs
    """
    baseline_paths = baseline_export.get("derived_topk", [])
    fork_paths = fork_export.get("derived_topk", [])

    baseline_seqs = {p["edge_id_sequence"] for p in baseline_paths}
    fork_seqs = {p["edge_id_sequence"] for p in fork_paths}

    removed = baseline_seqs - fork_seqs
    remaining = fork_paths

    # Highest remaining confidence band
    band_order = ["VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW", "INSUFFICIENT"]
    highest_band = "INSUFFICIENT"
    for p in remaining:
        band = p.get("confidence_band", "INSUFFICIENT")
        if band_order.index(band) < band_order.index(highest_band):
            highest_band = band

    # Evidence coverage from fork
    fork_edges = fork_export.get("edges", [])
    total_edges = len(fork_edges)

    # Map band to display label
    band_labels = {
        "VERY_HIGH": "Very High",
        "HIGH": "High",
        "MEDIUM": "Medium",
        "LOW": "Low",
        "VERY_LOW": "Very Low",
        "INSUFFICIENT": "Insufficient",
    }

    total_baseline = len(baseline_paths)
    removed_count = len(removed)
    removed_pct = round(100 * removed_count / max(1, total_baseline))

    # Placeholder coverage — computed from fork export if available
    # Look for evidence_coverage in the fork export's warnings or compute from edges
    coverage_pct = 0
    # Try to extract from the export structure (JSON output computes this)
    fork_obs_digests = fork_export.get("obs_digests", {})
    if total_edges > 0:
        # Count edges with obs_digests (at least one observation)
        coverage_pct = round(100 * len(fork_obs_digests) / total_edges)

    control_roi_line = (
        f"Control ROI: {removed_count} of Top-K paths removed ({removed_pct}%), "
        f"highest remaining path confidence: {band_labels.get(highest_band, highest_band)}, "
        f"evidence coverage: {coverage_pct}% of edges observed."
    )

    # Edge diffs
    edge_diffs = _compute_edge_diffs(baseline_export, fork_export)

    return {
        "paths_removed": removed_count,
        "paths_remaining": len(remaining),
        "highest_remaining_band": highest_band,
        "removed_pct": removed_pct,
        "evidence_coverage_pct": coverage_pct,
        "control_roi_line": control_roi_line,
        "edge_diffs": edge_diffs,
    }


def _compute_edge_diffs(
    baseline: dict[str, Any],
    fork: dict[str, Any],
) -> list[dict]:
    """Find edges whose beliefs changed between baseline and fork."""
    baseline_edges = {e["edge_id"]: e for e in baseline.get("edges", [])}
    fork_edges = {e["edge_id"]: e for e in fork.get("edges", [])}

    diffs = []
    for eid in sorted(set(baseline_edges) | set(fork_edges)):
        b = baseline_edges.get(eid)
        f = fork_edges.get(eid)

        if b is None or f is None:
            diffs.append({"edge_id": eid, "change": "added_or_removed"})
            continue

        if (b["alpha_i"] != f["alpha_i"] or b["beta_i"] != f["beta_i"]
                or b["status"] != f["status"] or b["frozen"] != f["frozen"]):
            diffs.append({
                "edge_id": eid,
                "change": "belief_changed",
                "baseline_alpha": b["alpha_i"],
                "baseline_beta": b["beta_i"],
                "fork_alpha": f["alpha_i"],
                "fork_beta": f["beta_i"],
                "baseline_status": b["status"],
                "fork_status": f["status"],
            })

    return diffs
