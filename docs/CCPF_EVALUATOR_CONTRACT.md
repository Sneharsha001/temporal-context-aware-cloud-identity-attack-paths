# Formal CCPF Evaluator Contract
## Restricted Deterministic Constraint Evaluator (RDCE) Interface and Semantic Specification

**Document Version:** 1.1.0 (Prompt 2A Corrections Applied)  
**Phase:** Prompt 2 / 2A — Evaluator Contract Definition  
**Research Workspace:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`  
**Working Branch:** `temporal-context-dev`  
**Baseline Anchor:** ARF-RT v1.2 (`04d2bae12f600ff48b6054aa513878ea5dc72b16`)  
**Date:** 2026-10-12  
**Status:** Approved Specification — Gated for Prompt 3 Implementation  

---

## 1. Architectural Role and Scope

This document defines the formal contract for the **Restricted Deterministic Constraint Evaluator (RDCE)**, the core evaluation procedure for **Context-Conditioned Path Feasibility (CCPF)** in cloud identity attack paths.

### 1.1 Feasibility Filter vs. Probability Scoring
The RDCE operates as a purely logical feasibility filter over candidate path prefixes $P_n = \langle e_1, \dots, e_n \rangle$:
- It evaluates whether the operational context required across a path prefix is satisfiable under declared scope and transition models.
- **Strict Decoupling from Probability Scoring:** The RDCE interface returns **no probability multipliers**. It outputs purely logical decisions: $\text{status} \in \{\text{SAT}, \text{UNSAT}, \text{UNKNOWN}\}$ accompanied by diagnostic evidence (witness, contradiction rationale, or unknown rationale).
- Downstream search policies (e.g., in future engine integration) may use a sound $\text{UNSAT}$ verdict to justify pruning, but this is an external engine search decision, not an evaluator probability calculation.
- **Zero Fixed-Point Underflow Conflation:** Fixed-point underflow ($p_{\text{worst\_q8}} = 0$) in ARF-RT's Bayesian path search is an integer arithmetic rounding effect. The RDCE remains strictly independent of Q8 probability arithmetic, and numerical zero is never treated as a logical infeasibility signal.

---

## 2. Evaluator Interface Contract

### 2.1 Input Data Contract
The evaluator consumes an immutable data structure defining the sequence of evaluated hops, context requirements, produced states, transition relations, and scenario assumptions.

```python
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum

class ContextScope(str, Enum):
    REQUEST = "request"        # Per-API-call origin (e.g., aws:SourceIp)
    SESSION = "session"        # Bound to active STS token set (e.g., aws:MultiFactorAuthPresent)
    PRINCIPAL = "principal"    # Bound to active IAM entity (e.g., aws:PrincipalTag/<key>)
    CONFIG = "config"          # Hop-local request parameter (e.g., sts:ExternalId)
    UNKNOWN = "unknown"        # Unmapped or unclassified scope

@dataclass(frozen=True)
class ContextPredicate:
    key: str                   # Condition key (e.g., "aws:SourceIp", "aws:PrincipalTag/Department")
    operator: str              # Supported operator (e.g., "IpAddress", "NotIpAddress", "StringEquals", "Bool", "Null")
    values: List[str]          # Literal comparison values (e.g., ["10.0.0.0/8"])
    scope: ContextScope        # Declared formal scope
    description: Optional[str] = None

@dataclass(frozen=True)
class ProducedStateModification:
    key: str                   # State variable key (e.g., "active_principal", "network_execution_origin")
    operation: str             # "SET", "CLEAR", "RESET"
    value: str                 # Literal target value (e.g., "10.0.1.100")
    attributes: Dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None

@dataclass(frozen=True)
class HopContextSpec:
    hop: int                   # 1-indexed sequence number
    edge_type: str             # IAM action / pivot (e.g., "sts:AssumeRole", "s3:GetObject")
    src_node_id: str           # Source graph node ID
    dst_node_id: str           # Destination graph node ID
    required_context: List[ContextPredicate] = field(default_factory=list)
    produced_context: List[ProducedStateModification] = field(default_factory=list)

@dataclass(frozen=True)
class TransitionRelation:
    from_hop: int              # Predecessor hop
    to_hop: int                # Successor hop
    variable: str              # Related context variable
    relation_type: str         # "EQUAL", "PIVOT_TRANSITION", "IDENTITY_DERIVATION"
    formula: str               # Formal transition invariant
    rationale: Optional[str] = None

@dataclass(frozen=True)
class PathEvaluationInput:
    path_id: str
    hops: List[HopContextSpec]
    transition_constraints: List[TransitionRelation] = field(default_factory=list)
    scenario_assumptions: Dict[str, Any] = field(default_factory=dict)
```

### 2.2 Output Data Contract
The evaluator returns an explicit logical verdict, structured evidence, and diagnostic metadata:

```python
class FeasibilityStatus(str, Enum):
    SAT = "SAT"          # Provably satisfiable under the supported model and explicit assumptions
    UNSAT = "UNSAT"      # Provably contradictory under the supported model and explicit assumptions
    UNKNOWN = "UNKNOWN"  # Undecidable, unsupported operator/key, incomplete metadata, or timeout

@dataclass(frozen=True)
class PathEvaluationResult:
    path_id: str
    status: FeasibilityStatus
    witness: Optional[Dict[str, Any]] = None              # Valid assignment mapping (REQUIRED if SAT)
    contradiction_rationale: Optional[str] = None         # Formal clash proof (REQUIRED if UNSAT)
    unknown_rationale: Optional[str] = None               # Root cause of undecidability (REQUIRED if UNKNOWN)
    evaluated_hops: int = 0                               # Number of hops evaluated before decision
    solver_duration_ms: float = 0.0                       # Measured wall-clock evaluation duration
    timeout_occurred: bool = False                        # True if iteration/time ceiling was triggered
    diagnostic_metadata: Dict[str, Any] = field(default_factory=dict)
```

**Key Invariant:** Notice that `PathEvaluationResult` contains **no probability multiplier**. Feasibility is strictly separated from probability scoring.

---

## 3. The Safe Input Fragment Grammar

The RDCE supports a sound, decidable, domain-restricted subset of IAM policy conditions. If any condition, operator, or key in the input falls outside this subset, the evaluator **must reject the input to `UNKNOWN`**. Under no circumstances may an unsupported condition be simplified or silently converted into an `UNSAT` verdict.

### 3.1 Operator Specifications

#### 1. `IpAddress`
- **Applicable Keys:** `aws:SourceIp` (or validated network-origin keys).
- **Scope:** `ContextScope.REQUEST`.
- **Accepted Value Format:** List of valid IPv4 (or IPv6) CIDR strings (e.g., `["10.0.0.0/8"]`, `["192.168.1.0/24", "10.0.0.0/16"]`). Single IP literals (e.g. `"10.0.1.50"`) are treated as `/32` CIDRs.
- **Multi-Value Semantics:** **Disjunctive (OR)** in accordance with AWS IAM policy evaluation semantics:
  $$\text{Eval}(\text{IpAddress}(k, [S_1, \dots, S_n]), IP) \iff IP \in \bigcup_{i=1}^n S_i$$
- **Cross-Predicate Composition:** Multiple `IpAddress` predicates applied to the same IP variable (e.g., across sequential hops under the static origin assumption) are **Conjunctive (AND)**:
  $$IP \in \left( \bigcup S_i \right) \cap \left( \bigcup S'_j \right)$$
- **Contradiction Condition:** $\left( \bigcup S_i \right) \cap \left( \bigcup S'_j \right) = \emptyset \implies \text{UNSAT}$.
- **Rejection to UNKNOWN:** Malformed CIDR strings (e.g., `"10.0.0.256/24"`), mixed IPv4/IPv6 comparisons without explicit dual-stack semantics, or non-string values.

#### 2. `NotIpAddress`
- **Applicable Keys:** `aws:SourceIp`.
- **Scope:** `ContextScope.REQUEST`.
- **Accepted Value Format:** List of valid CIDR strings.
- **Multi-Value Semantics:** **Conjunctive Negation (AND NOT)** in accordance with De Morgan's laws for AWS `NotIpAddress`:
  $$\text{Eval}(\text{NotIpAddress}(k, [S_1, \dots, S_n]), IP) \iff IP \notin \bigcup_{i=1}^n S_i$$
- **Composition with `IpAddress`:** When a variable is constrained by both `IpAddress` ($S_{\text{allow}}$) and `NotIpAddress` ($S_{\text{deny}}$):
  $$IP \in S_{\text{allow}} \setminus S_{\text{deny}}$$
- **Contradiction Condition:** $S_{\text{allow}} \subseteq S_{\text{deny}} \implies S_{\text{allow}} \setminus S_{\text{deny}} = \emptyset \implies \text{UNSAT}$.
- **Rejection to UNKNOWN:** Same format errors as `IpAddress`.

#### 3. `StringEquals`
- **Applicable Keys:** String-valued keys in principal, session, or config scopes (e.g., `aws:PrincipalTag/<key>`, `sts:ExternalId`, `aws:PrincipalArn`).
- **Scope:** `PRINCIPAL`, `SESSION`, or `CONFIG`.
- **Accepted Value Format:** List of string literals (e.g., `["ApplicationDevelopment"]`, `["Engineering", "DevOps"]`).
- **Multi-Value Semantics:** **Disjunctive (OR)** set membership:
  $$\text{Eval}(\text{StringEquals}(k, [v_1, \dots, v_n]), x) \iff x \in \{v_1, \dots, v_n\}$$
- **Contradiction Condition:** Two `StringEquals` constraints on the same scalar variable requiring sets $V_1$ and $V_2$ where $V_1 \cap V_2 = \emptyset \implies \text{UNSAT}$.
- **Rejection to UNKNOWN:** Non-string values, non-scalar variables.

#### 4. `StringLike` (Restricted)
- **Safe Fragment Restriction:** `StringLike` is supported **only when values contain NO wildcards** (`*` or `?`).
- When wildcard-free, it is semantically identical to `StringEquals`.
- **Rejection to UNKNOWN:** If any value in a `StringLike` predicate contains `*` or `?`, the RDCE immediately rejects the evaluation to `UNKNOWN(unsupported_wildcard_operator)`.

#### 5. `Bool`
- **Applicable Keys:** `aws:MultiFactorAuthPresent`.
- **Scope:** `ContextScope.SESSION`.
- **Accepted Value Format:** List containing `"true"` or `"false"` (case-insensitive string or boolean).
- **Multi-Value Semantics:** Single value enforces exact boolean truth; `["true", "false"]` is vacuously true.
- **Contradiction Condition:** Active session requires $\text{true} \land \text{false} \implies \text{UNSAT}$.
- **Rejection to UNKNOWN:** Any key other than recognized boolean flags, unparseable truth strings.

#### 6. `Null`
- **Applicable Keys:** Any supported condition key.
- **Accepted Value Format:** `["true"]` (key must be absent/null) or `["false"]` (key must exist).
- **Contradiction Condition:** A key required to be absent ($\text{Null}(k) == \text{true}$) while simultaneously required to have a concrete value by `IpAddress`, `StringEquals`, or `Bool` yields $\text{UNSAT}$.
- **Rejection to UNKNOWN:** Non-boolean value arguments.

### 3.2 Composition Across Keys and Hops
- **Hop-Level Conjunction:** All `required_context` predicates on a single hop $e_i$ must be simultaneously satisfied: $\text{Req}(e_i) = \bigwedge_{p \in \text{predicates}} p(\Sigma_i)$.
- **Inter-Hop Conjunction:** The path constraint store conjoins requirements across all hops, subject to variable lifecycle and transition axioms:
  $$\Phi(P_m) = \bigwedge_{i=1}^m \text{Req}(e_i) \land \bigwedge_{i=2}^m T(e_{i-1} \to e_i)$$

---

## 4. Context Scope Taxonomy and Lifecycle Mechanics

Variables are partitioned into four formal scopes with explicit lifecycle rules:

```
+------------------------------------------------------------------------------------+
|                                 CONTEXT SCOPES                                     |
+------------------------------------------------------------------------------------+
| Scope                  | Lifecycle / Bound Entity       | Primary Examples         |
+------------------------+--------------------------------+--------------------------+
| Request (R)            | Per-API-call origin            | aws:SourceIp             |
| Session (S)            | Active STS credential set      | aws:MultiFactorAuth      |
| Principal (P)          | Active IAM identity            | aws:PrincipalTag/<key>   |
| Configuration (C)      | Hop-local call parameter       | sts:ExternalId           |
+------------------------------------------------------------------------------------+
```

### 4.1 Request Scope ($\mathcal{R}$) Lifecycle
- **Default Invariant:** API calls are independently routed. Without an explicit scenario assumption, $\mathcal{R}_1[\text{SourceIp}]$ and $\mathcal{R}_2[\text{SourceIp}]$ are independent free variables.
- **Static Origin Assumption:** If and only if the scenario declares `static_origin_assumption = True` (as in CE1 and CE2), the frame axiom enforces:
  $$\forall i, j: \mathcal{R}_i[\text{aws:SourceIp}] = \mathcal{R}_j[\text{aws:SourceIp}]$$
- **Network Pivot:** If a hop specifies an explicit `PIVOT_TRANSITION` (as in CE3), the successor request IP is re-bound to the target host's internal IP ($IP_{i+1} = \text{Produced}(e_i)[\text{HostIP}]$). This breaks the static origin chain without contradiction.

### 4.2 Session Scope ($\mathcal{S}$) Lifecycle
- **Persistence:** Carried across standard actions executed using the same temporary credential set.
- **AssumeRole Transition:** When `sts:AssumeRole` is executed, a *new* STS session token is minted. Prior session attributes do not persist unless explicitly modeled STS session tagging or chaining applies.

### 4.3 Principal Scope ($\mathcal{P}$) Lifecycle
- **Persistence:** Carried across standard actions performed by the active identity.
- **AssumeRole Transition:** Upon assuming a role, the active principal resets to the assumed role identity.
- **Session Tag Prohibition (CE6):** If the target role's trust policy enforces `Null(aws:RequestTag/<key>) == true` (or the caller lacks `sts:TagSession`), the active principal tag is strictly bounded to the target role's static attached tags.

### 4.4 Configuration Scope ($\mathcal{C}$) Lifecycle
- **Hop-Local Parameter:** `sts:ExternalId` is a caller-supplied parameter evaluated against the target trust policy.
- **Non-Interference Invariant:** Supplying `ExternalId = "ClientA"` to assume Role A on Hop 1 and `ExternalId = "ClientB"` to assume Role B on Hop 2 are separate API calls. They do not share state, do not carry forward, and **never contradict**.

---

## 5. Tri-State Semantics: SAT, UNSAT, UNKNOWN

### 5.1 Formal Definitions
- **SAT:** A mathematically verified constructive assignment $w$ exists satisfying all accumulated constraints:
  $$\text{RDCE}(\Phi) = \text{SAT} \implies \exists w: w \models \Phi$$
  *Requirement:* The evaluator MUST return a non-empty `witness` dictionary demonstrating satisfiability.
- **UNSAT:** A sound mathematical proof demonstrates that no valid assignment can satisfy the conjunction of constraints under the declared model and explicit scenario assumptions:
  $$\text{RDCE}(\Phi) = \text{UNSAT} \implies \Phi \vdash \bot$$
  *Requirement:* The evaluator MUST return a `contradiction_rationale` describing the clashing constraints.
- **UNKNOWN:** The evaluator cannot soundly decide satisfiability within the Safe Fragment. This occurs when:
  - An unsupported condition operator or key is encountered.
  - Context metadata is absent or malformed.
  - A variable is unconstrained by required continuity assumptions.
  - An evaluation timeout or unhandled exception occurs.
  *Requirement:* The evaluator MUST return an `unknown_rationale` explaining why the case was undecidable.

### 5.2 Error and Timeout Handling Contract
- **Bounded Iteration:** Maximum 1,000 constraint checks per path prefix.
- **Exception Trap:** Any runtime error (`ValueError`, `KeyError`, `IndexError`) must be caught cleanly and return:
  `status = UNKNOWN, timeout_occurred = ..., unknown_rationale = str(exception)`.
- **CRITICAL SOUNDNESS INVARIANT:** A solver error, exception, or timeout **MUST NEVER BE RETURNED AS UNSAT**. Converting uncertainty into UNSAT would falsely prune valid attack paths.

---

## 6. Distinction: Isolated Evaluator Behavior vs. Integrated Non-Perturbation

To avoid overclaiming, we draw a strict distinction between isolated unit evaluation and integrated engine behavior:

### 6.1 Isolated Evaluator Behavior on Absent Context (CE5)
- In isolated testing, evaluating a scenario with zero context metadata (e.g., baseline `diamond_scenario.json`) results in `UNKNOWN(unknown_rationale="NO_CONTEXT_CONSTRAINTS_DEFINED")`.
- This confirms that the evaluator gracefully handles legacy fixtures without false pruning.

### 6.2 Future Integration Non-Perturbation
- Demonstrating that baseline Top-$K$ ranking and exact Q8 probability scores are completely unchanged across entire legacy graphs is a property of the **integrated Best-First search engine**.
- This claim requires an empirical regression comparison against the untouched `ARF-RT-BASELINE` mirror (`04d2bae`), which can only be conducted after engine integration is authorized.
- The isolated evaluator returning `UNKNOWN` on CE5 is a necessary prerequisite, but does **NOT** by itself prove integrated Top-$K$ equivalence.

---

## 7. Categorization of System Guarantees

| Category | Property / Claim | Evidence & Status |
|---|---|---|
| **Formal Property** | Monotonicity of Conjunction ($\Phi \land \phi \vdash \bot$ if $\Phi \vdash \bot$) | Mathematically proven in classical logic. |
| **Formal Property** | Soundness of Interval Disjointness ($S_1 \cap S_2 = \emptyset \implies \bot$) | Mathematically proven over IPv4 address spaces. |
| **Explicit Assumption** | Static Attacker Origin across sequential hops (CE1, CE2) | Scenario-level premise declared in fixture metadata. |
| **Explicit Assumption** | Trust policy prohibition on session tagging (CE6) | Scenario-level premise declared in fixture metadata. |
| **Design Target** | Worst-case complexity $O(m \cdot k)$ for $m$ hops and $k$ CIDRs | Theoretical upper bound. Microsecond runtime is an **unbenchmarked design target**, NOT an empirical achievement. |
| **Open Proof Obligation** | O1: Solver Soundness over Safe Fragment | Requires empirical unit testing in Prompt 3/4. |
| **Open Proof Obligation** | O6 / O7: Search Admissibility and Top-$K$ Completeness | **OPEN**. Conjunction monotonicity alone does not prove Top-$K$ completeness in the presence of integer underflow and tie-breaking. |

---

## 8. Fixture-to-Contract Mapping (CE1–CE6)

| Fixture ID & Name | Input Files | Expected Status | Specific Semantics Tested | Explicit Assumptions Required | Formal Caveats & Limitations |
|---|---|---|---|---|---|
| **CE1**: Compatible Persistent Context | `ce1_compatible_persistent.scenario.json`, `ce1_compatible_persistent.context.json` | **SAT** | CIDR intersection non-emptiness ($10.0.0.0/8 \cap 10.1.0.0/16 \ne \emptyset$) | Static origin assumption: Attacker operates from single fixed IP | SAT indicates local CIDR compatibility; does not guarantee end-to-end reachability. |
| **CE2**: Contradictory Persistent Context | `ce2_contradictory_persistent.scenario.json`, `ce2_contradictory_persistent.context.json` | **UNSAT** | CIDR disjointness ($10.0.0.0/8 \cap 192.168.0.0/16 = \emptyset$) | Static origin assumption: Attacker cannot switch IPs between hops | If an attacker controls multiple egress IPs, the physical attack might remain viable. |
| **CE3**: Context-Changing Transition Permitted | `ce3_transition_permitted.scenario.json`, `ce3_transition_permitted.context.json` | **SAT** | Network pivot transition: $\mathcal{R}_2[\text{SourceIp}] = \text{HostIP} = 10.0.1.100$ | Traversing hop 1 re-binds execution origin to internal bastion VPC IP | Depends on explicit `PIVOT_TRANSITION` annotation in sidecar. |
| **CE4**: Missing or Unsupported Context Metadata | `ce4_unsupported_metadata.scenario.json`, `ce4_unsupported_metadata.context.json` | **UNKNOWN** | Rejection of unmodeled operator (`UnsupportedFuzzyMatch`) and key (`vendor:...`) | Evaluator must not crash or deduce false UNSAT | Conservative fallback preserves paths without pruning. |
| **CE5**: Baseline Compatibility | Baseline fixtures (`diamond_scenario.json`, `primary_realistic_scenario.json`), `ce5_baseline_compatibility.context.json` | **UNKNOWN** | Absence of context metadata yields UNKNOWN | Zero-sidecar scenarios evaluate uniformly to UNKNOWN | Demonstrates isolated fallback; integrated non-perturbation requires separate baseline diff. |
| **CE6**: Principal Scope Boundary Across AssumeRole | `ce6_principal_scope_boundary.scenario.json`, `ce6_principal_scope_boundary.context.json` | **UNSAT** | Identity pivot resets $\mathcal{P}$; target role tag clashes with required secret tag | 1. Trust policy enforces `Null(RequestTag)`. 2. Caller lacks `sts:TagSession`. 3. Role tag static. | UNSAT depends strictly on explicit trust policy constraint forbidding session tag pass-through. |

---

## 9. Implementation Acceptance Tests (A1–A8)

Any prototype implementation in Prompt 3 must pass the following eight deterministic tests:

- **Test A1 (CIDR Disjointness Soundness):** Verifies that two disjoint IPv4 subnets under static origin return `UNSAT` with a non-empty `contradiction_rationale` (CE2).
- **Test A2 (CIDR Subset Compatibility):** Verifies that nested or overlapping IPv4 subnets under static origin return `SAT` with a concrete `witness` IP dictionary (CE1).
- **Test A3 (Pivot Transition Re-Binding):** Verifies that a network pivot transition updates the request-scoped IP and returns `SAT` without falsely clashing with the pre-pivot IP (CE3).
- **Test A4 (Unsupported Operator Fallback):** Verifies that an unmodeled condition operator yields `UNKNOWN` with an explicit `unknown_rationale` without raising an uncaught exception (CE4).
- **Test A5 (Baseline Fixture Isolated Fallback):** Verifies that unannotated baseline scenarios uniformly yield `UNKNOWN` with `unknown_rationale="NO_CONTEXT_CONSTRAINTS_DEFINED"` (CE5).
- **Test A6 (Principal Scope Reset Clash):** Verifies that an AssumeRole transition with prohibited session tags resets $\mathcal{P}$ and detects principal tag contradictions as `UNSAT` with clear rationale (CE6).
- **Test A7 (Decoupling from Underflow):** Verifies that candidate paths with $p_{\text{worst\_q8}} = 0$ maintain their logical feasibility status (`SAT` or `UNKNOWN`) and are never converted to `UNSAT`.
- **Test A8 (Robustness and Exception Trapping):** Verifies that malformed JSON, corrupted IPs, and empty edge lists return `UNKNOWN` with `timeout_occurred=False` and never raise uncaught exceptions.

---

## 10. Summary Contract Status

**CONTRACT STATUS: APPROVED (PROMPT 2A CORRECTIONS APPLIED)**  
- Probability multipliers removed from evaluator interface and acceptance tests.  
- Safe input fragment formalized with precise multi-value and composition semantics.  
- Isolated CE5 behavior distinguished from future integrated non-perturbation.  
- System guarantees separated into formal properties, explicit assumptions, design targets, and open proof obligations.  
- Production engine source code (`arf_rt/engine/paths.py`) and baseline mirror (`ARF-RT-BASELINE`) remain 100% untouched.  
