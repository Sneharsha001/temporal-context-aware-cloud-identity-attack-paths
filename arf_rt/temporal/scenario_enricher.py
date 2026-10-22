"""
arf_rt/temporal/scenario_enricher.py - Enrich scenario edges with TemporalHints.

Provides a bridge between ARF-RT's scenario/edge representation and the
temporal evaluation layer.  Given a list of scenario edges and a
corresponding set of CloudTrail event records, this module:

1. Parses CloudTrail events into TemporalHints via cloudtrail_parser.
2. Attempts to match each scenario edge to its corresponding hint using
   ARN-based key matching.
3. Returns a complete hints dict usable by TemporalEvaluator.

When no CloudTrail match is found for an edge, an empty TemporalHint
(all None) is returned so the evaluator treats it as UNKNOWN.
"""

from __future__ import annotations

import re
from typing import Any

from arf_rt.temporal.cloudtrail_parser import extract_hints_from_log
from arf_rt.temporal.hints import TemporalHint


# Regex to extract 12-digit AWS account IDs from ARN strings
_ACCOUNT_RE = re.compile(r":(\d{12}):")


def _normalize_arn(arn: str) -> str:
    """Lower-case and strip whitespace from an ARN for comparison."""
    return arn.strip().lower()


def enrich_edges_with_hints(
    edge_ids: list[str],
    cloudtrail_events: list[dict[str, Any]],
    fallback_hint: TemporalHint | None = None,
) -> dict[str, TemporalHint]:
    """
    Build a TemporalHint dict for a set of scenario edge IDs using
    CloudTrail events as the data source.

    Matching strategy
    -----------------
    CloudTrail-derived hint edge IDs are in the form
    ``<source-ARN>→<target-ARN>``.  Scenario edge IDs may use any format,
    but if they embed ARN fragments the matcher will attempt substring
    matching against parsed CloudTrail edge IDs.

    Parameters
    ----------
    edge_ids:
        Ordered list of scenario edge identifiers.
    cloudtrail_events:
        Raw CloudTrail event dicts (from JSON export or API).
    fallback_hint:
        Hint to use when no CloudTrail match is found. Defaults to an
        empty TemporalHint (all None fields).

    Returns
    -------
    dict[str, TemporalHint]
        Mapping from scenario edge ID to its TemporalHint.
    """
    ct_hints = extract_hints_from_log(cloudtrail_events)
    ct_keys_lower = {k.lower(): v for k, v in ct_hints.items()}

    result: dict[str, TemporalHint] = {}
    for eid in edge_ids:
        # Direct match (case-insensitive)
        lower_eid = _normalize_arn(eid)
        if lower_eid in ct_keys_lower:
            hint = ct_keys_lower[lower_eid]
            result[eid] = TemporalHint(
                edge_id=eid,
                earliest_observed=hint.earliest_observed,
                latest_observed=hint.latest_observed,
                credential_issued=hint.credential_issued,
                credential_expiry=hint.credential_expiry,
                last_used=hint.last_used,
            )
            continue

        # Substring match — find any CT hint whose key contains this edge ID
        matched: TemporalHint | None = None
        for ct_key, ct_hint in ct_keys_lower.items():
            if lower_eid in ct_key or ct_key in lower_eid:
                matched = ct_hint
                break

        if matched is not None:
            result[eid] = TemporalHint(
                edge_id=eid,
                earliest_observed=matched.earliest_observed,
                latest_observed=matched.latest_observed,
                credential_issued=matched.credential_issued,
                credential_expiry=matched.credential_expiry,
                last_used=matched.last_used,
            )
        else:
            result[eid] = fallback_hint or TemporalHint(edge_id=eid)

    return result


def hint_coverage_report(
    edge_ids: list[str],
    hints: dict[str, TemporalHint],
) -> dict[str, Any]:
    """
    Return a dict describing what fraction of edges have temporal data.

    Parameters
    ----------
    edge_ids:
        The full set of scenario edge IDs.
    hints:
        The enriched hint dict returned by enrich_edges_with_hints.

    Returns
    -------
    dict with keys:
        total, with_observation, with_credential_lifetime,
        with_last_used, coverage_pct
    """
    total = len(edge_ids)
    obs = sum(1 for eid in edge_ids if hints.get(eid, TemporalHint()).has_observation_window())
    cred = sum(1 for eid in edge_ids if hints.get(eid, TemporalHint()).has_credential_lifetime())
    lu = sum(1 for eid in edge_ids if (hints.get(eid, TemporalHint()).last_used is not None))
    coverage = obs / total if total else 0.0
    return {
        "total": total,
        "with_observation": obs,
        "with_credential_lifetime": cred,
        "with_last_used": lu,
        "coverage_pct": round(coverage * 100, 1),
    }
