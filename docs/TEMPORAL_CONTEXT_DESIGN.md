# Temporal Context Design Specification

**Module:** `arf_rt.temporal`  
**Status:** Active Research (Prompt 10+)  
**Branch:** `temporal-context-dev`  
**Version:** 0.1.0

---

## 1. Motivation

Classic CCPF evaluates whether a path is *logically* feasible (CIDR blocks, MFA presence, principal tags). It does not examine *when* each hop could occur. Temporal constraints add a complementary feasibility dimension: even if each hop is logically possible, the *sequence* may be impossible because credentials expire, sessions overlap impossibly, or CloudTrail timestamps contradict the assumed ordering.

**Goal:** Reduce false-positive attack paths further by pruning temporally infeasible sequences without altering Bayesian probability scores for feasible paths.

---

## 2. Temporal Constraint Model

### 2.1 Hop-Level Timestamps

Each edge in the graph can carry an optional `temporal_hint`:

```python
@dataclass
class TemporalHint:
    earliest_observed: datetime | None   # earliest CloudTrail event time
    latest_observed:   datetime | None   # latest CloudTrail event time
    credential_issued: datetime | None   # STS AssumeRole response time
    credential_expiry: datetime | None   # issued + MaxSessionDuration
    last_used:         datetime | None   # IAM credential last-used timestamp
```

### 2.2 Path-Level Temporal Constraints

For an ordered path `π = [e₁, e₂, ..., eₙ]`, the following constraints are evaluated:

| ID | Name | Formula |
|----|------|---------|
| TC-1 | **Causal Order** | `∀i < j: t_observed(eᵢ) < t_observed(eⱼ)` |
| TC-2 | **Session Validity** | `t_observed(eᵢ) < credential_expiry(eᵢ₋₁)` |
| TC-3 | **Minimum Velocity** | `t_observed(eᵢ) - t_observed(eᵢ₋₁) > δ_min` |
| TC-4 | **Stale Credential** | `now - last_used(eᵢ) < τ_stale` |
| TC-5 | **Concurrent Session** | No two hops share session token in overlapping windows |

### 2.3 Constraint Evaluation Logic

```python
def evaluate_temporal_constraints(
    path: list[Edge],
    hints: dict[EdgeId, TemporalHint],
    config: TemporalConfig,
) -> TemporalVerdict:
    """
    Returns FEASIBLE, INFEASIBLE(reason), or UNKNOWN (missing data).

    UNKNOWN paths are not pruned — they pass through to the Bayesian
    layer unchanged to preserve recall at the cost of precision.
    """
    ...
```

---

## 3. Integration with CCPF

Temporal evaluation is a **post-filter** that runs after the CCPF evaluator:

```
PathCandidates
      │
      ▼
  CCPF Evaluator (logical constraints: CIDR, MFA, tags)
      │ FEASIBLE
      ▼
  Temporal Evaluator (time constraints: ordering, expiry, velocity)
      │ FEASIBLE
      ▼
  Bayesian Scorer (probability update)
      │
      ▼
  Top-K Ranking
```

**Invariant:** The temporal layer may only *reduce* the candidate set. It must not alter the probability of paths it passes through.

---

## 4. Configuration Schema

```python
@dataclass
class TemporalConfig:
    min_hop_delta_seconds: float = 0.5       # TC-3 minimum velocity (seconds)
    stale_credential_days: int   = 90        # TC-4 stale threshold
    unknown_passthrough:   bool  = True      # Pass UNKNOWN through (True = recall-favoring)
    enabled_constraints:   set[str] = field(
        default_factory=lambda: {"TC-1", "TC-2", "TC-3", "TC-4", "TC-5"}
    )
```

---

## 5. Proof Obligations

| PO | Statement |
|----|-----------|
| PO-T1 | If `TC-1` fires, the path cannot have occurred in CloudTrail → INFEASIBLE is sound. |
| PO-T2 | If `unknown_passthrough=True`, recall is preserved: no true positive is pruned. |
| PO-T3 | Temporal evaluation is idempotent: evaluating the same path twice yields the same verdict. |
| PO-T4 | Temporal evaluation does not modify Bayesian belief state. |

---

## 6. Open Research Questions

1. **Timestamp Availability:** CloudTrail data is often sparse. What fraction of real attack paths have sufficient timestamps to evaluate TC-1 through TC-5?
2. **Bot vs. Human Velocity:** Is δ_min = 0.5s the right threshold for distinguishing automated vs. human-driven privilege escalation?
3. **Clock Skew Tolerance:** How should the evaluator handle multi-account CloudTrail events with clock skew up to ±30s?
4. **Retroactive Feasibility:** If a path was feasible at time T but credentials have since expired, is the path still a security finding?

---

## 7. References

- [CCPF Integration Design](CCPF_PATH_LEVEL_INTEGRATION_DESIGN.md)
- [CCPF API Reference](CCPF_API_REFERENCE.md)
- [Threat Model](THREAT_MODEL.md)
- AWS CloudTrail Event Reference: https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/
- AWS STS AssumeRole: https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html
