"""ARF-RT canonical enums (spec §5).

Every enum value is a pinned canonical string.
If any enum string changes, SEMANTICS_VERSION must be bumped.
"""

from enum import Enum

SEMANTICS_VERSION: str = "1.0.0"


class _StrEnum(str, Enum):
    """String enum base that serializes to its value."""

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"


# §5.2 ProbeType (MVP)
class ProbeType(_StrEnum):
    REPLAY_SCRIPTED = "REPLAY_SCRIPTED"
    WHATIF_FORCED = "WHATIF_FORCED"


# §5.3 ObservationStrength
class ObservationStrength(_StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    DIRECT = "DIRECT"
    INFERRED = "INFERRED"
    HEURISTIC = "HEURISTIC"


# §5.4 ObservationResult
class ObservationResult(_StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ERROR = "ERROR"
    INCONCLUSIVE = "INCONCLUSIVE"


# §5.5 ReasonClass
class ReasonClass(_StrEnum):
    CONSTRAINT_DENY = "CONSTRAINT_DENY"
    MISSING_PERMISSION = "MISSING_PERMISSION"
    CONDITION_MISMATCH = "CONDITION_MISMATCH"
    TRANSIENT = "TRANSIENT"
    THROTTLED = "THROTTLED"
    UNKNOWN = "UNKNOWN"


# §5.6 EdgeStatus
class EdgeStatus(_StrEnum):
    HYPOTHESIZED = "HYPOTHESIZED"
    CONFIRMED = "CONFIRMED"
    REFUTED = "REFUTED"
    UNKNOWN_CONDITION = "UNKNOWN_CONDITION"


# §5.7 ConstraintStatus
class ConstraintStatus(_StrEnum):
    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"


# §5.8 ConstraintValidationStatus
class ConstraintValidationStatus(_StrEnum):
    UNVALIDATED = "UNVALIDATED"
    VALIDATED = "VALIDATED"
    ASSUMED = "ASSUMED"


# §5.9 RelationType (optional but recommended)
class RelationType(_StrEnum):
    APPLIES_TO = "APPLIES_TO"
    DEPENDS_ON = "DEPENDS_ON"


# §10 Observation polarity (updater classification)
class ObsPolarity(_StrEnum):
    SUPPORT = "SUPPORT"
    AGAINST = "AGAINST"
    NEUTRAL = "NEUTRAL"


# Run mode (§1.2)
class RunMode(_StrEnum):
    REPLAY_ONLY = "REPLAY_ONLY"


# Warning severity (§7.9)
class WarningSeverity(_StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


# Confidence band labels (reporting; §16)
class ConfidenceBand(_StrEnum):
    VERY_HIGH = "VERY_HIGH"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    VERY_LOW = "VERY_LOW"
    INSUFFICIENT = "INSUFFICIENT"
