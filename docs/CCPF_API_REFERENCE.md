# CCPF API Reference Guide

## Module: `research.ccpf.rdce`

The **Relational Deterministic Constraint Evaluator (RDCE)** implements formal constraint checking for multi-hop privilege edges.

### Data Contracts

#### `PathEvaluationInput`
Input specification provided to evaluate a candidate attack path.

```python
@dataclass(frozen=True)
class PathEvaluationInput:
    path_id: str
    hops: tuple[HopContextSpec, ...]
    transition_constraints: tuple[TransitionConstraintSpec, ...] = ()
    scenario_assumptions: Mapping[str, Any] = field(default_factory=dict)
```

**Attributes:**
- `path_id`: Unique identifier for the evaluated path.
- `hops`: Sequence of ordered hop specifications from attacker initial access to target.
- `transition_constraints`: Constraints governing valid transitions across role-assumption boundaries.
- `scenario_assumptions`: Global environment bindings (e.g., origin network CIDR, caller credentials).

#### `PathEvaluationVerdict`
Enumeration of constraint satisfaction outcomes:
- `FEASIBLE`: Path satisfies all policy constraints under the given scenario assumptions.
- `INFEASIBLE`: Path violates at least one constraint (with explicit witness recorded).
- `INDETERMINATE`: Insufficient context to decide conclusively; defaults to permissive baseline.

---

## Module: `arf_rt.ccpf_bridge`

Bridge connecting the low-level RDCE evaluator to the ARF-RT graph traversal engine.

### `evaluate_candidate_hop(hop_spec: HopContextSpec, assumptions: Mapping[str, Any]) -> HopAuditRecord`
Evaluates a single candidate traversal edge during passive audit mode.

### Invariants:
1. **Zero-Pruning Invariant:** In passive audit mode, no graph edges are removed or probability weights modified.
2. **Determinism Invariant:** Repeated evaluations with identical inputs produce identical verdicts and audit witnesses.
