"""
arf_rt/temporal/cloudtrail_parser.py - CloudTrail event parser for temporal hints.

Extracts TemporalHint objects from raw CloudTrail event records.  Only
AssumeRole and AssumeRoleWithWebIdentity events are currently handled.

This module is intentionally dependency-free (no boto3 required) — it
operates on pre-fetched event dictionaries that can come from any source
(local JSON files, S3, CloudTrail Lake queries, etc.).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


from arf_rt.temporal.hints import TemporalHint


# Supported CloudTrail event names for credential lifecycle tracking
_ASSUME_ROLE_EVENTS: frozenset[str] = frozenset(
    {
        "AssumeRole",
        "AssumeRoleWithWebIdentity",
        "AssumeRoleWithSAML",
    }
)

# ISO-8601 pattern accepted by CloudTrail
_CT_TS_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(Z|[+-]\d{2}:\d{2})$"
)


def _parse_ct_timestamp(ts: str) -> datetime | None:
    """
    Parse a CloudTrail ISO-8601 timestamp into a UTC-aware datetime.
    Returns None on any parse failure to keep the caller's logic simple.
    """
    try:
        # datetime.fromisoformat does not handle 'Z' in Python < 3.11
        normalised = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalised)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _extract_role_arn(event: dict[str, Any]) -> str:
    """
    Best-effort extraction of the assumed role ARN from an AssumeRole event.
    Falls back to the event's requestParameters.roleArn or an empty string.
    """
    rp = event.get("requestParameters") or {}
    return rp.get("roleArn", "")


def parse_assume_role_event(event: dict[str, Any]) -> TemporalHint | None:
    """
    Convert a single CloudTrail event dict into a TemporalHint.

    Parameters
    ----------
    event:
        A CloudTrail event as a Python dict (e.g., loaded from JSON).

    Returns
    -------
    TemporalHint or None
        Returns None if the event is not an AssumeRole-family event or
        if the eventTime field is missing or unparsable.
    """
    event_name = event.get("eventName", "")
    if event_name not in _ASSUME_ROLE_EVENTS:
        return None

    event_time_str = event.get("eventTime")
    event_time = _parse_ct_timestamp(event_time_str) if event_time_str else None
    if event_time is None:
        return None

    # Build edge ID from source principal + target role ARN
    user_identity = event.get("userIdentity") or {}
    source_arn = user_identity.get("arn", "unknown-principal")
    target_arn = _extract_role_arn(event)
    edge_id = f"{source_arn}→{target_arn}"

    # Extract STS credential lifetime from responseElements
    response = event.get("responseElements") or {}
    creds = response.get("credentials") or {}
    expiry_str = creds.get("expiration")
    expiry = _parse_ct_timestamp(expiry_str) if expiry_str else None

    return TemporalHint(
        edge_id=edge_id,
        earliest_observed=event_time,
        latest_observed=event_time,
        credential_issued=event_time,
        credential_expiry=expiry,
        last_used=event_time,
    )


def extract_hints_from_log(events: list[dict[str, Any]]) -> dict[str, TemporalHint]:
    """
    Process a list of CloudTrail event dicts and return a dict of
    TemporalHints keyed by edge ID.

    When multiple events map to the same edge ID, the earliest observation
    window start and latest observation window end are preserved, while
    the most recent credential issuance is used.

    Parameters
    ----------
    events:
        Raw CloudTrail event records (as dicts).

    Returns
    -------
    dict[str, TemporalHint]
        Mapping from edge_id to TemporalHint for use with TemporalEvaluator.
    """
    accumulated: dict[str, list[TemporalHint]] = {}
    for event in events:
        hint = parse_assume_role_event(event)
        if hint is None:
            continue
        accumulated.setdefault(hint.edge_id, []).append(hint)

    result: dict[str, TemporalHint] = {}
    for edge_id, hints in accumulated.items():
        earliest = min(
            (h.earliest_observed for h in hints if h.earliest_observed is not None),
            default=None,
        )
        latest = max(
            (h.latest_observed for h in hints if h.latest_observed is not None),
            default=None,
        )
        # Most recent issuance → most current credential expiry
        latest_hint = max(
            (h for h in hints if h.credential_issued is not None),
            key=lambda h: h.credential_issued,  # type: ignore[arg-type,return-value]
            default=hints[-1],
        )
        result[edge_id] = TemporalHint(
            edge_id=edge_id,
            earliest_observed=earliest,
            latest_observed=latest,
            credential_issued=latest_hint.credential_issued,
            credential_expiry=latest_hint.credential_expiry,
            last_used=latest,
        )
    return result
