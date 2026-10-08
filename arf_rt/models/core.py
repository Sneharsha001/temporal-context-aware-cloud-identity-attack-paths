"""Pydantic models for ARF-RT domain objects (spec §§5-7).

All models enforce invariants at construction time:
  - extra="forbid" rejects unknown fields (spec §19.1)
  - Integer-only domains for signal_q, confidence_q
  - Enum validation via string matching
  - JSON fields must be canonical at write time

These models are used for scenario ingest validation.
DB rows are read as sqlite3.Row dicts — models are for write-path validation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from arf_rt.config import (
    CONFIDENCE_Q_MAX,
    CONFIDENCE_Q_MIN,
    DEFAULT_ALPHA_I,
    DEFAULT_BETA_I,
    REGION_NULL_SENTINEL,
    SIGNAL_Q_MAX,
    SIGNAL_Q_MIN,
)
from arf_rt.models.enums import (
    ConstraintStatus,
    ConstraintValidationStatus,
    EdgeStatus,
    ObservationResult,
    ObservationStrength,
    ProbeType,
    ReasonClass,
    RelationType,
    WarningSeverity,
)
from arf_rt.util.canon import (
    ARFValidationError,
    canonical_json,
    features_fp as compute_features_fp,
    make_flags_json,
    properties_fp as compute_properties_fp,
    region_norm,
)


class _StrictBase(BaseModel):
    """Base model: forbid extra fields, validate assignment."""

    model_config = ConfigDict(extra="forbid", validate_default=True)


# ===================================================================
# Scenario ingest models (what the JSON provides)
# ===================================================================


class NodeInput(_StrictBase):
    """A node in the scenario JSON (spec §18)."""

    provider: str
    node_type: str
    provider_id: str
    region: str | None = None
    display_name: str = ""
    properties: dict | None = None

    @field_validator("region", mode="before")
    @classmethod
    def normalize_region(cls, v: str | None) -> str:
        return region_norm(v)


class TemplateInput(_StrictBase):
    """A template definition in the scenario JSON."""

    provider: str
    edge_type: str
    features: dict
    feature_schema_version: int = 1
    alpha_agg_i: int = DEFAULT_ALPHA_I
    beta_agg_i: int = DEFAULT_BETA_I


class EdgeInput(_StrictBase):
    """An edge in the scenario JSON (spec §18)."""

    edge_type: str
    src: str | dict  # node_id string or reference tuple
    dst: str | dict  # node_id string or reference tuple
    region: str | None = None
    features: dict | None = None
    alpha_i: int = DEFAULT_ALPHA_I
    beta_i: int = DEFAULT_BETA_I
    status: str = EdgeStatus.HYPOTHESIZED
    frozen: bool = False

    @field_validator("region", mode="before")
    @classmethod
    def normalize_region(cls, v: str | None) -> str:
        return region_norm(v)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        try:
            return EdgeStatus(v).value
        except ValueError:
            raise ARFValidationError(
                f"Invalid edge status: {v!r}. "
                f"Must be one of: {[e.value for e in EdgeStatus]}"
            )

    @field_validator("alpha_i", "beta_i", mode="before")
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        if isinstance(v, bool):
            raise ARFValidationError("alpha_i/beta_i must be int, got bool")
        if isinstance(v, float):
            raise ARFValidationError(
                f"alpha_i/beta_i must be int, got float"
            )
        if not isinstance(v, int):
            raise ARFValidationError(
                f"alpha_i/beta_i must be int, got {type(v).__name__}"
            )
        if v < 0:
            raise ARFValidationError(f"alpha_i/beta_i must be >= 0, got {v}")
        return v


class ConstraintInput(_StrictBase):
    """A constraint in the scenario JSON (spec §7.5)."""

    provider: str
    constraint_type: str
    scope_type: str
    scope_id: str
    region: str | None = None
    properties: dict | None = None
    status: str = ConstraintStatus.ACTIVE
    validation_status: str = ConstraintValidationStatus.UNVALIDATED
    confidence_q: int = 0

    @field_validator("region", mode="before")
    @classmethod
    def normalize_region(cls, v: str | None) -> str:
        return region_norm(v)

    @field_validator("confidence_q", mode="before")
    @classmethod
    def validate_confidence_q(cls, v: int) -> int:
        if isinstance(v, bool):
            raise ARFValidationError("confidence_q must be int, got bool")
        if isinstance(v, float):
            raise ARFValidationError("confidence_q must be int, got float")
        if not isinstance(v, int):
            raise ARFValidationError(
                f"confidence_q must be int, got {type(v).__name__}"
            )
        if v < CONFIDENCE_Q_MIN or v > CONFIDENCE_Q_MAX:
            raise ARFValidationError(
                f"confidence_q must be {CONFIDENCE_Q_MIN}..{CONFIDENCE_Q_MAX}, "
                f"got {v}"
            )
        return v


class EdgeConstraintInput(_StrictBase):
    """Links an edge to a constraint (spec §7.6)."""

    edge_ref: str | dict  # edge_id or reference
    constraint_ref: str | dict  # constraint_id or reference
    relation_type: str = RelationType.APPLIES_TO

    @field_validator("relation_type")
    @classmethod
    def validate_relation_type(cls, v: str) -> str:
        try:
            return RelationType(v).value
        except ValueError:
            raise ARFValidationError(
                f"Invalid relation_type: {v!r}. "
                f"Must be one of: {[e.value for e in RelationType]}"
            )


class NodeRef(_StrictBase):
    """A node reference by tuple fields (spec §18.2)."""

    provider: str
    node_type: str
    provider_id: str
    region: str | None = None


class ObjectiveInput(_StrictBase):
    """An objective in the scenario JSON (spec §18)."""

    objective_type: str
    start_nodes: list[str | dict]  # node_id strings or NodeRef dicts
    target_nodes: list[str | dict]  # node_id strings or NodeRef dicts
    max_depth: int
    k: int

    @field_validator("max_depth", "k", mode="before")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        if isinstance(v, bool):
            raise ARFValidationError("max_depth/k must be int, got bool")
        if not isinstance(v, int):
            raise ARFValidationError(
                f"max_depth/k must be int, got {type(v).__name__}"
            )
        if v <= 0:
            raise ARFValidationError(f"max_depth/k must be > 0, got {v}")
        return v


class ObservationInput(_StrictBase):
    """An observation in the scenario JSON (spec §18)."""

    edge_ref: str | dict  # edge_id or reference
    probe_type: str = ProbeType.REPLAY_SCRIPTED
    result: str
    reason_class: str = ReasonClass.UNKNOWN
    strength: str
    signal_q: int
    is_counterfactual: bool = False
    constraint_relevant: bool = False
    evidence_hash: str | None = None
    observed_at: str | None = None  # ISO 8601 timestamp; used for belief decay

    @field_validator("probe_type")
    @classmethod
    def validate_probe_type(cls, v: str) -> str:
        try:
            return ProbeType(v).value
        except ValueError:
            raise ARFValidationError(
                f"Invalid probe_type: {v!r}. "
                f"Must be one of: {[e.value for e in ProbeType]}"
            )

    @field_validator("result")
    @classmethod
    def validate_result(cls, v: str) -> str:
        try:
            return ObservationResult(v).value
        except ValueError:
            raise ARFValidationError(
                f"Invalid result: {v!r}. "
                f"Must be one of: {[e.value for e in ObservationResult]}"
            )

    @field_validator("reason_class")
    @classmethod
    def validate_reason_class(cls, v: str) -> str:
        try:
            return ReasonClass(v).value
        except ValueError:
            raise ARFValidationError(
                f"Invalid reason_class: {v!r}. "
                f"Must be one of: {[e.value for e in ReasonClass]}"
            )

    @field_validator("strength")
    @classmethod
    def validate_strength(cls, v: str) -> str:
        try:
            return ObservationStrength(v).value
        except ValueError:
            raise ARFValidationError(
                f"Invalid strength: {v!r}. "
                f"Must be one of: {[e.value for e in ObservationStrength]}"
            )

    @field_validator("signal_q", mode="before")
    @classmethod
    def validate_signal_q(cls, v: int) -> int:
        if isinstance(v, bool):
            raise ARFValidationError("signal_q must be int, got bool")
        if isinstance(v, float):
            raise ARFValidationError(
                "signal_q must be int, got float (spec §18.3: floats rejected)"
            )
        if not isinstance(v, int):
            raise ARFValidationError(
                f"signal_q must be int, got {type(v).__name__}"
            )
        if v < SIGNAL_Q_MIN or v > SIGNAL_Q_MAX:
            raise ARFValidationError(
                f"signal_q must be {SIGNAL_Q_MIN}..{SIGNAL_Q_MAX}, got {v}"
            )
        return v


class ScenarioInput(_StrictBase):
    """Top-level scenario JSON structure (spec §18)."""

    nodes: list[NodeInput]
    edges: list[EdgeInput]
    templates: list[TemplateInput] | None = None
    constraints: list[ConstraintInput] | None = None
    edge_constraints: list[EdgeConstraintInput] | None = None
    objectives: list[ObjectiveInput]
    observations: list[ObservationInput] | None = None
    metadata: dict | None = None

    @model_validator(mode="after")
    def require_at_least_one_objective(self) -> "ScenarioInput":
        if not self.objectives:
            raise ARFValidationError(
                "Scenario must have at least one objective (spec §18)"
            )
        return self


class RunWarningInput(_StrictBase):
    """A warning generated during processing."""

    code: str
    severity: str = WarningSeverity.WARN
    message: str = ""
    context: dict | None = None

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        try:
            return WarningSeverity(v).value
        except ValueError:
            raise ARFValidationError(
                f"Invalid severity: {v!r}. "
                f"Must be one of: {[e.value for e in WarningSeverity]}"
            )
