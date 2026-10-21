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

__all__ = [
    "TemporalHint",
    "TemporalConfig",
    "TemporalVerdict",
    "VerdictKind",
    "TemporalEvaluator",
]
