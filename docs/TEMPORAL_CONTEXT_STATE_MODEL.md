# Temporal Context State Model
## ARF-RT Research Extension — State Model Specification

**Branch:** `temporal-context-dev`
**Baseline:** ARF-RT v1.2
**Status:** Design only. Phase 14.1 Review applied. No implementation performed.
**Purpose:** Formal definition of the context state model for the proposed Context-Aware Attack-Path Feasibility extension.

---

## Phase 14.1 Review Findings

The state model has been drastically simplified to address fundamental flaws in temporal reasoning and data provenance.

### Major Changes
1. **Temporal Execution Dropped:** The baseline records `observed_at` (evidence collection time). It does not model actual attack execution time. We cannot mathematically evaluate whether a 1-hour STS session has expired if we do not know when the attacker assumed the role relative to subsequent actions. All inter-hop temporal expiration modeling has been removed and categorized as UNKNOWN / Future Work.
2. **Strict CSP Mathematics:** We abandoned arbitrary fractional probabilities for partial overlaps. Compatibility is now a strict Constraint-Satisfaction Problem (CSP) outputting either `1.0` (feasible/unknown) or `0.0` (impossible).
3. **Context Scope Defined:** Explicitly categorized context into Request, Session, Principal, and Configuration scopes to avoid incorrectly persisting transient state across boundaries.

---

## 1. Operational Context — Definition and Scope

"Operational context" refers to the set of condition key-value pairs required for an API call to succeed.

### 1.1 Context Scopes

The model categorizes conditions based on their persistence and mutability:

1. **Request-Scoped (Mutable):** `aws:SourceIp`, `aws:CurrentTime`. Evaluated dynamically on every request.
   - *Transition Rule:* Does not automatically persist. To compare across hops, we must explicitly assume the attacker uses static infrastructure (no pivots).
2. **Session-Scoped (Persistent for session):** `aws:MultiFactorAuthPresent`. Evaluated at credential issuance.
   - *Transition Rule:* Persists for the lifetime of the specific STS session token.
3. **Principal-Scoped (Persistent):** `aws:PrincipalTag`.
   - *Transition Rule:* Changes across `sts:AssumeRole` unless Transitive Tag Keys are explicitly modeled.
4. **Configuration-Scoped (Static):** `sts:ExternalId`. A requirement of the trust policy, not an attacker-carried state.
   - *Transition Rule:* Evaluated only at the specific edge. Does not propagate.

### 1.2 Minimal Implementable Attribute Set

```
OperationalContext := {
    condition_key   : str          # e.g., "aws:SourceIp"
    operator        : str | None   # e.g., "StringEquals", "IpAddress"
    required_value  : str | None   # e.g., "10.0.0.0/8"
}
```

*Data Provenance Note:* The standard ARF-RT baseline fixtures do not populate these specific rich attributes. Research-specific fixtures must be generated to evaluate this model.

---

## 2. RequiredContext, ProducedContext, and CarriedContext

### 2.1 RequiredContext(edge)

The set of condition key-value pairs required to traverse an edge.

```
RequiredContext(e) = parse_condition_keys(properties_json(constraints linked to e))
```

### 2.2 ProducedContext(edge)

The state an attacker acquires and carries forward after traversing an edge.

**State carried across AssumeRole (M2 Resolved):**
- **Identity:** The principal ARN changes.
- **Session Context:** MFA presence propagates if the role was assumed with MFA.
- **Request Context:** `aws:SourceIp` evaluates the network origin of the *request*. 
  *Assumption:* We assume the attacker executes subsequent requests from the same origin infrastructure. Therefore, `aws:SourceIp` persists in the `CarriedContext` unless a pivot node is encountered.

### 2.3 CarriedContext(path_prefix)

The cumulative context available to the next hop.

```
CarriedContext([]) = {}
CarriedContext([e_1, ..., e_n]) = merge(CarriedContext([e_1, ..., e_{n-1}]),
                                        ProducedContext(e_n))
```

---

## 3. Compatibility CSP Model (Correction 3)

A context transition occurs when the path extends from edge `e_{n-1}` to edge `e_n`.

```
compatibility_factor = evaluate_transition(
    carried  : CarriedContext([e_1, ..., e_{n-1}]),
    required : RequiredContext(e_n)
)
```

### 3.1 COMPATIBLE / UNKNOWN (Fallback)
- **Condition:** Carried context explicitly satisfies the required context, OR Carried context lacks the information to evaluate the requirement, OR `RequiredContext` is empty/unparseable.
- **Output:** `compatibility_factor = 1.0`.
- **Reasoning:** We preserve the baseline Bayesian probability. Unknown context does not prove feasibility, but failing back to the baseline ensures we do not arbitrarily penalize paths based on missing data.

### 3.2 CONFLICTING
- **Condition:** Carried context logically contradicts the required context (e.g., disjoint IP subnets `10.0.0.0/8` vs `192.168.0.0/16`).
- **Output:** `compatibility_factor = 0.0`.
- **Reasoning:** In a Bayesian network, a physically impossible sequence has a probability of exactly zero.

### 3.3 PARTIALLY OVERLAPPING
- **Condition:** Required context is narrower than Carried context (e.g., Carried `/8`, Required `/24`).
- **Output:** Treated as **UNKNOWN** (`1.0`). 
- **Reasoning:** Without a known probability distribution for the attacker's location within the `/8` subnet, inventing a fractional probability is mathematically unsound. 

---

## 4. Summary Table: Proposed vs. Baseline Behavior

| Behavior | ARF-RT v1.2 Baseline | Proposed Extension | Notes |
|----------|---------------------|-------------------|-------|
| Observation decay | `2^(-age/90)` applied | Unchanged | Not modified |
| Correlation | constraint_id sharing ONLY | constraint_id sharing ONLY | Context union-find rejected |
| Condition evaluation | Never | CSP Evaluation | Requires new research fixtures |
| Partial Overlap Prob | N/A | Treated as Unknown (1.0) | Avoids inventing probabilities |
| Conflicting Context | Ignored (false positives) | Drops sequence (0.0) | CSP elimination |
| Temporal Expiration | Not modelled | Not modelled | Execution time unknown |
| Admissibility Bound | Guaranteed | Preserved | Multiplier is strictly {0,1} |

**NO CODE IMPLEMENTATION HAS BEEN PERFORMED.**
