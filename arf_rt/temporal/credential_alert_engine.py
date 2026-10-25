"""
arf_rt/temporal/credential_alert_engine.py - Rule-based alerting on credential risk scores.

Evaluates CredentialRiskScore results against configurable threshold rules and
emits structured Alert objects suitable for SIEM forwarding, Slack webhooks,
or file-based audit trails.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Sequence

from arf_rt.temporal.credential_scorer import CredentialRiskScore


class AlertSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class Alert:
    """A triggered alert for a single credential edge."""

    edge_id: str
    severity: AlertSeverity
    rule_name: str
    message: str
    score: float
    triggered_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def to_dict(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "severity": self.severity.value,
            "rule_name": self.rule_name,
            "message": self.message,
            "score": self.score,
            "triggered_at": self.triggered_at.isoformat(),
        }


@dataclass
class AlertRule:
    """A single threshold-based alert rule."""

    name: str
    severity: AlertSeverity
    predicate: Callable[[CredentialRiskScore], bool]
    message_template: str  # may reference {edge_id} and {score}

    def evaluate(self, result: CredentialRiskScore) -> Alert | None:
        if self.predicate(result):
            return Alert(
                edge_id=result.edge_id,
                severity=self.severity,
                rule_name=self.name,
                message=self.message_template.format(
                    edge_id=result.edge_id,
                    score=result.score,
                    label=result.label,
                ),
                score=result.score,
            )
        return None


# ---------------------------------------------------------------------------
# Default rule set
# ---------------------------------------------------------------------------

DEFAULT_RULES: list[AlertRule] = [
    AlertRule(
        name="CRITICAL_SCORE",
        severity=AlertSeverity.CRITICAL,
        predicate=lambda r: r.score >= 0.80,
        message_template=(
            "Credential edge '{edge_id}' has a CRITICAL temporal risk score of {score:.4f}. "
            "Immediate rotation or revocation is recommended."
        ),
    ),
    AlertRule(
        name="HIGH_SCORE",
        severity=AlertSeverity.HIGH,
        predicate=lambda r: 0.60 <= r.score < 0.80,
        message_template=(
            "Credential edge '{edge_id}' has a HIGH temporal risk score of {score:.4f}. "
            "Schedule rotation within 24 hours."
        ),
    ),
    AlertRule(
        name="EXPIRED_CREDENTIAL",
        severity=AlertSeverity.CRITICAL,
        predicate=lambda r: r.expiry_factor >= 1.0,
        message_template=(
            "Credential edge '{edge_id}' has an expiry factor of 1.0 — the credential is expired. "
            "Any active session using this edge must be terminated."
        ),
    ),
    AlertRule(
        name="HIGHLY_STALE",
        severity=AlertSeverity.HIGH,
        predicate=lambda r: r.staleness_factor >= 0.90,
        message_template=(
            "Credential edge '{edge_id}' has not been rotated recently (staleness={score:.4f}). "
            "Enforce rotation policy."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Alert Engine
# ---------------------------------------------------------------------------

class CredentialAlertEngine:
    """
    Evaluates scored credential edges against alert rules and collects triggered alerts.

    Parameters
    ----------
    rules:
        List of :class:`AlertRule` instances to evaluate. Defaults to
        :data:`DEFAULT_RULES` when omitted.
    deduplicate:
        When True, suppress duplicate alerts for the same (edge_id, rule_name) pair.
    """

    def __init__(
        self,
        rules: list[AlertRule] | None = None,
        *,
        deduplicate: bool = True,
    ) -> None:
        self.rules = rules if rules is not None else DEFAULT_RULES
        self.deduplicate = deduplicate
        self._seen: set[tuple[str, str]] = set()

    def evaluate(self, results: Sequence[CredentialRiskScore]) -> list[Alert]:
        """Run all rules against every scored result and return triggered alerts."""
        alerts: list[Alert] = []
        for result in results:
            for rule in self.rules:
                alert = rule.evaluate(result)
                if alert is None:
                    continue
                key = (alert.edge_id, alert.rule_name)
                if self.deduplicate and key in self._seen:
                    continue
                self._seen.add(key)
                alerts.append(alert)
        return alerts

    def reset(self) -> None:
        """Clear deduplication state so the engine can be reused across batches."""
        self._seen.clear()

    def evaluate_single(self, result: CredentialRiskScore) -> list[Alert]:
        """Convenience wrapper to evaluate a single scored result."""
        return self.evaluate([result])

    def alerts_by_severity(
        self,
        results: Sequence[CredentialRiskScore],
    ) -> dict[AlertSeverity, list[Alert]]:
        """Return alerts grouped by severity level."""
        all_alerts = self.evaluate(results)
        grouped: dict[AlertSeverity, list[Alert]] = {s: [] for s in AlertSeverity}
        for alert in all_alerts:
            grouped[alert.severity].append(alert)
        return grouped
