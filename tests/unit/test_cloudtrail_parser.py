"""
tests/unit/test_cloudtrail_parser.py - Unit tests for arf_rt.temporal.cloudtrail_parser.

Verifies parse_assume_role_event and extract_hints_from_log with realistic
CloudTrail event structures.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from arf_rt.temporal.cloudtrail_parser import (
    extract_hints_from_log,
    parse_assume_role_event,
)


# ---------------------------------------------------------------------------
# Sample event builders
# ---------------------------------------------------------------------------


def make_assume_role_event(
    source_arn: str = "arn:aws:iam::111111111111:user/alice",
    target_arn: str = "arn:aws:iam::222222222222:role/DevRole",
    event_time: str = "2025-06-15T10:00:00Z",
    expiry: str | None = "2025-06-15T11:00:00Z",
    event_name: str = "AssumeRole",
) -> dict[str, Any]:
    response_elements: dict[str, Any] = {}
    if expiry is not None:
        response_elements["credentials"] = {"expiration": expiry}
    return {
        "eventName": event_name,
        "eventTime": event_time,
        "userIdentity": {"arn": source_arn},
        "requestParameters": {"roleArn": target_arn},
        "responseElements": response_elements,
    }


# ---------------------------------------------------------------------------
# parse_assume_role_event
# ---------------------------------------------------------------------------


class TestParseAssumeRoleEvent:
    def test_returns_hint_for_valid_event(self) -> None:
        event = make_assume_role_event()
        hint = parse_assume_role_event(event)
        assert hint is not None

    def test_edge_id_contains_source_and_target(self) -> None:
        hint = parse_assume_role_event(make_assume_role_event())
        assert hint is not None
        assert "alice" in hint.edge_id or "111111111111" in hint.edge_id
        assert "DevRole" in hint.edge_id or "222222222222" in hint.edge_id

    def test_earliest_and_latest_both_set_to_event_time(self) -> None:
        hint = parse_assume_role_event(make_assume_role_event(event_time="2025-06-15T10:00:00Z"))
        assert hint is not None
        expected = datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        assert hint.earliest_observed == expected
        assert hint.latest_observed == expected

    def test_credential_expiry_parsed(self) -> None:
        hint = parse_assume_role_event(
            make_assume_role_event(expiry="2025-06-15T11:00:00Z")
        )
        assert hint is not None
        assert hint.credential_expiry == datetime(2025, 6, 15, 11, 0, 0, tzinfo=timezone.utc)

    def test_no_expiry_results_in_none(self) -> None:
        hint = parse_assume_role_event(make_assume_role_event(expiry=None))
        assert hint is not None
        assert hint.credential_expiry is None

    def test_non_assume_role_event_returns_none(self) -> None:
        event = make_assume_role_event(event_name="GetCallerIdentity")
        assert parse_assume_role_event(event) is None

    def test_missing_event_time_returns_none(self) -> None:
        event = make_assume_role_event()
        del event["eventTime"]
        assert parse_assume_role_event(event) is None

    def test_assume_role_with_web_identity(self) -> None:
        event = make_assume_role_event(event_name="AssumeRoleWithWebIdentity")
        hint = parse_assume_role_event(event)
        assert hint is not None

    def test_assume_role_with_saml(self) -> None:
        event = make_assume_role_event(event_name="AssumeRoleWithSAML")
        hint = parse_assume_role_event(event)
        assert hint is not None


# ---------------------------------------------------------------------------
# extract_hints_from_log
# ---------------------------------------------------------------------------


class TestExtractHintsFromLog:
    def test_empty_log_returns_empty_dict(self) -> None:
        assert extract_hints_from_log([]) == {}

    def test_single_event_produces_single_hint(self) -> None:
        events = [make_assume_role_event()]
        hints = extract_hints_from_log(events)
        assert len(hints) == 1

    def test_non_assume_role_events_ignored(self) -> None:
        events = [
            make_assume_role_event(event_name="GetCallerIdentity"),
            make_assume_role_event(),
        ]
        hints = extract_hints_from_log(events)
        assert len(hints) == 1

    def test_multiple_events_same_edge_merged(self) -> None:
        # Same source → target, two different times
        events = [
            make_assume_role_event(event_time="2025-06-15T08:00:00Z"),
            make_assume_role_event(event_time="2025-06-15T10:00:00Z"),
        ]
        hints = extract_hints_from_log(events)
        # Should collapse to a single edge_id
        assert len(hints) == 1
        hint = next(iter(hints.values()))
        assert hint.earliest_observed == datetime(2025, 6, 15, 8, 0, 0, tzinfo=timezone.utc)
        assert hint.latest_observed == datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

    def test_different_edges_produce_separate_hints(self) -> None:
        events = [
            make_assume_role_event(
                source_arn="arn:aws:iam::111:user/alice",
                target_arn="arn:aws:iam::222:role/RoleA",
            ),
            make_assume_role_event(
                source_arn="arn:aws:iam::222:role/RoleA",
                target_arn="arn:aws:iam::333:role/RoleB",
            ),
        ]
        hints = extract_hints_from_log(events)
        assert len(hints) == 2
