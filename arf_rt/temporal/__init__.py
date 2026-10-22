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
from arf_rt.temporal.audit_log import AuditRecord, TemporalAuditLog
from arf_rt.temporal.metrics import TemporalMetrics
from arf_rt.temporal.export import (
    export_audit_log_to_csv,
    export_metrics_to_csv,
    export_metrics_to_dict,
    generate_summary_table,
)

__all__ = [
    "TemporalHint",
    "TemporalConfig",
    "TemporalVerdict",
    "VerdictKind",
    "TemporalEvaluator",
    "TemporalPathFilter",
    "FilterResult",
    "TemporalAuditLog",
    "AuditRecord",
    "TemporalMetrics",
    "export_metrics_to_dict",
    "export_metrics_to_csv",
    "export_audit_log_to_csv",
    "generate_summary_table",
]
