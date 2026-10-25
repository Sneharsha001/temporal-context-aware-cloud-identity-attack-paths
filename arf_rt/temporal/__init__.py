"""
arf_rt/temporal/__init__.py - Temporal context sub-package for ARF-RT.

Re-exports the primary public interface for temporal path feasibility
evaluation. Import as::

    from arf_rt.temporal import TemporalEvaluator, TemporalConfig, TemporalVerdict
"""

from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.config import TemporalConfig
from arf_rt.temporal.verdict import TemporalVerdict, VerdictKind
from arf_rt.temporal.evaluator import TemporalEvaluator
from arf_rt.temporal.path_filter import FilterResult, TemporalPathFilter
from arf_rt.temporal.audit_log import AuditEntry, TemporalAuditLog
from arf_rt.temporal.metrics import TemporalMetrics
from arf_rt.temporal.summary import TemporalSummaryReporter
from arf_rt.temporal.timeline import CredentialTimelineBuilder, TimelineEvent
from arf_rt.temporal.anomaly_classifier import (
    AnomalyClassifier,
    ClassifiedAnomaly,
    SeverityTier,
)
from arf_rt.temporal.batch_runner import PathFeasibilityBatchRunner, ScenarioBatchResult
from arf_rt.temporal.export import (
    export_audit_log_to_csv,
    export_metrics_to_csv,
    export_metrics_to_dict,
    generate_summary_table,
)
from arf_rt.temporal.credential_scorer import CredentialScorer, CredentialRiskScore
from arf_rt.temporal.temporal_exporter import TemporalExporter
from arf_rt.temporal.credential_alert_engine import (
    Alert,
    AlertRule,
    AlertSeverity,
    CredentialAlertEngine,
)
from arf_rt.temporal.temporal_drift_detector import (
    DriftEvent,
    DriftKind,
    DriftReport,
    TemporalDriftDetector,
)
from arf_rt.temporal.policy_window_validator import (
    PolicyConfig,
    PolicyValidationResult,
    PolicyViolation,
    PolicyWindowValidator,
)
from arf_rt.temporal.coverage_reporter import (
    CoverageReport,
    CoverageReporter,
    FieldCoverage,
)
from arf_rt.temporal.temporal_dashboard import TemporalDashboard

__all__ = [
    "TemporalHint",
    "TemporalConfig",
    "TemporalVerdict",
    "VerdictKind",
    "TemporalEvaluator",
    "TemporalPathFilter",
    "FilterResult",
    "TemporalAuditLog",
    "AuditEntry",
    "TemporalMetrics",
    "TemporalSummaryReporter",
    "CredentialTimelineBuilder",
    "TimelineEvent",
    "AnomalyClassifier",
    "ClassifiedAnomaly",
    "SeverityTier",
    "PathFeasibilityBatchRunner",
    "ScenarioBatchResult",
    "export_metrics_to_dict",
    "export_metrics_to_csv",
    "export_audit_log_to_csv",
    "generate_summary_table",
    "CredentialScorer",
    "CredentialRiskScore",
    "TemporalExporter",
    "CredentialAlertEngine",
    "AlertRule",
    "Alert",
    "AlertSeverity",
    "TemporalDriftDetector",
    "DriftReport",
    "DriftEvent",
    "DriftKind",
    "PolicyWindowValidator",
    "PolicyConfig",
    "PolicyViolation",
    "PolicyValidationResult",
    "CoverageReporter",
    "CoverageReport",
    "FieldCoverage",
    "TemporalDashboard",
]
