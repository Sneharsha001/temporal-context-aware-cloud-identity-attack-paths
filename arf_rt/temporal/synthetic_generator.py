"""
arf_rt/temporal/synthetic_generator.py - Synthetic CloudTrail log generator.

Generates realistic AWS CloudTrail AssumeRole event streams for privilege graph
topologies with configurable timing parameters and synthetic anomaly injection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class SyntheticGeneratorConfig:
    """Settings for synthetic CloudTrail event generation."""
    base_time: datetime = field(
        default_factory=lambda: datetime(2026, 10, 24, 8, 0, 0, tzinfo=timezone.utc)
    )
    hop_interval_seconds: int = 60
    session_duration_seconds: int = 3600
    account_id: str = "111122223333"
    region: str = "us-east-1"


class CloudTrailSyntheticGenerator:
    """Generates synthetic CloudTrail event batches matching standard AWS schemas."""

    def __init__(self, config: SyntheticGeneratorConfig | None = None) -> None:
        self.config = config or SyntheticGeneratorConfig()

    def generate_event(
        self,
        source_principal: str,
        target_role: str,
        event_time: datetime,
        session_duration: int | None = None,
        region: str | None = None,
        source_ip: str = "198.51.100.5",
    ) -> dict[str, Any]:
        """Generate a single CloudTrail AssumeRole event record dictionary."""
        dur = session_duration or self.config.session_duration_seconds
        expiry = event_time + timedelta(seconds=dur)
        reg = region or self.config.region

        role_arn = (
            target_role
            if target_role.startswith("arn:aws:")
            else f"arn:aws:iam::{self.config.account_id}:role/{target_role}"
        )
        principal_arn = (
            source_principal
            if source_principal.startswith("arn:aws:")
            else f"arn:aws:iam::{self.config.account_id}:user/{source_principal}"
        )

        return {
            "eventVersion": "1.08",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAEXAMPLEQWERTY",
                "arn": principal_arn,
                "accountId": self.config.account_id,
            },
            "eventTime": event_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "eventSource": "sts.amazonaws.com",
            "eventName": "AssumeRole",
            "awsRegion": reg,
            "sourceIPAddress": source_ip,
            "userAgent": "aws-sdk-python/1.34.0",
            "requestParameters": {
                "roleArn": role_arn,
                "roleSessionName": "SyntheticSession",
                "durationSeconds": dur,
            },
            "responseElements": {
                "credentials": {
                    "accessKeyId": "ASIAEXAMPLEKEY123",
                    "expiration": expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            },
        }

    def generate_path_events(
        self,
        path_nodes: list[str],
        inject_anomaly: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Generate a sequential chain of AssumeRole events along a node path.

        Supported anomaly injections:
        - 'causal_inversion': second hop event occurs before first hop
        - 'session_expired': final hop occurs after previous session expired
        - 'concurrency': simultaneous calls from two disparate regions
        """
        if len(path_nodes) < 2:
            return []

        events: list[dict[str, Any]] = []
        current_time = self.config.base_time

        for i in range(len(path_nodes) - 1):
            source = path_nodes[i]
            target = path_nodes[i + 1]

            hop_time = current_time
            if inject_anomaly == "causal_inversion" and i == 1:
                # Invert: make hop 2 occur before hop 1
                hop_time = self.config.base_time - timedelta(minutes=10)
            elif inject_anomaly == "session_expired" and i == len(path_nodes) - 2:
                # Push event time beyond previous session expiration
                hop_time = current_time + timedelta(seconds=self.config.session_duration_seconds + 500)

            ev = self.generate_event(source, target, hop_time)
            events.append(ev)

            if inject_anomaly == "concurrency" and i == 0:
                # Add duplicate simultaneous call from ap-southeast-1
                dup_ev = self.generate_event(
                    source,
                    target,
                    hop_time,
                    region="ap-southeast-1",
                    source_ip="203.0.113.19",
                )
                events.append(dup_ev)

            current_time = hop_time + timedelta(seconds=self.config.hop_interval_seconds)

        return events
