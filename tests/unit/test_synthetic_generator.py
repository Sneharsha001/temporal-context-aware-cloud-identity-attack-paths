"""
tests/unit/test_synthetic_generator.py - Unit tests for CloudTrailSyntheticGenerator.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from arf_rt.temporal.cloudtrail_parser import parse_assume_role_event
from arf_rt.temporal.synthetic_generator import (
    CloudTrailSyntheticGenerator,
    SyntheticGeneratorConfig,
)


class TestCloudTrailSyntheticGenerator:
    def test_generate_event_valid_schema(self) -> None:
        gen = CloudTrailSyntheticGenerator()
        ev = gen.generate_event(
            source_principal="alice",
            target_role="DevRole",
            event_time=datetime(2026, 10, 24, 10, 0, 0, tzinfo=timezone.utc),
        )

        assert ev["eventName"] == "AssumeRole"
        assert ev["eventSource"] == "sts.amazonaws.com"
        assert "alice" in ev["userIdentity"]["arn"]
        assert "DevRole" in ev["requestParameters"]["roleArn"]
        assert "expiration" in ev["responseElements"]["credentials"]

        # Verify parser can read it back
        hint = parse_assume_role_event(ev)
        assert hint is not None
        assert hint.credential_expiry is not None

    def test_generate_path_events_nominal(self) -> None:
        gen = CloudTrailSyntheticGenerator()
        nodes = ["UserA", "RoleB", "RoleC"]
        events = gen.generate_path_events(nodes)

        assert len(events) == 2
        assert events[0]["eventTime"] < events[1]["eventTime"]

    def test_inject_causal_inversion(self) -> None:
        gen = CloudTrailSyntheticGenerator()
        nodes = ["UserA", "RoleB", "RoleC"]
        events = gen.generate_path_events(nodes, inject_anomaly="causal_inversion")

        assert len(events) == 2
        # Second event should occur before first event
        assert events[1]["eventTime"] < events[0]["eventTime"]

    def test_inject_concurrency(self) -> None:
        gen = CloudTrailSyntheticGenerator()
        nodes = ["UserA", "RoleB"]
        events = gen.generate_path_events(nodes, inject_anomaly="concurrency")

        assert len(events) == 2
        assert events[0]["eventTime"] == events[1]["eventTime"]
        assert events[0]["awsRegion"] != events[1]["awsRegion"]
