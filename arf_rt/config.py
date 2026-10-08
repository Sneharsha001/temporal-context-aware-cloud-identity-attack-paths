"""ARF-RT configuration constants (spec §§ various).

All thresholds, caps, and semantic constants live here.
No computation logic — just values.
"""

# §3.3 — Region normalization sentinel
REGION_NULL_SENTINEL: str = "-"

# §3.4 — Fixed-point scaling factor for probability ordering
Q8: int = 100_000_000

# §9.1 — Deterministic saturation values
SATURATION_ALPHA_ALLOW: int = 9900
SATURATION_BETA_ALLOW: int = 100
SATURATION_ALPHA_DENY: int = 100
SATURATION_BETA_DENY: int = 9900

# §9.2 — base_w_q by ObservationStrength (REPLAY_SCRIPTED)
BASE_W_Q: dict[str, int] = {
    "DETERMINISTIC": 100,
    "DIRECT": 95,
    "INFERRED": 60,
    "HEURISTIC": 30,
}

# §9.5 — Mass caps
MAX_EDGE_MASS: int = 20_000
MAX_TEMPLATE_MASS: int = 200_000

# §13.2 — Constraint validation defaults
DEFAULT_CONSTRAINT_N: int = 2  # min distinct edges
DEFAULT_CONSTRAINT_M: int = 2  # min distinct src_node_id values

# §14.2 — Correlation link minimum confidence
CORRELATION_LINK_MIN_CONFIDENCE_Q: int = 500  # 50% on 0..1000 scale

# §6.1 — SQLite PRAGMAs
SQLITE_BUSY_TIMEOUT_MS: int = 5000

# §19.1 — Input hardening
MAX_SCENARIO_SIZE_BYTES: int = 524_288_000  # 10 MB

# §3.4 — Quantization domains (strict)
SIGNAL_Q_MIN: int = 0
SIGNAL_Q_MAX: int = 100
CONFIDENCE_Q_MIN: int = 0
CONFIDENCE_Q_MAX: int = 1000

# §9.1 — Default priors for new edges
DEFAULT_ALPHA_I: int = 1
DEFAULT_BETA_I: int = 1

# §20.1 — Belief decay (opt-in via --as-of)
DECAY_HALF_LIFE_DAYS: float = 90.0   # 90 days = quarterly reassessment cycle
DECAY_MIN_WEIGHT: float = 0.01       # floor: never decay below 1% of original weight
