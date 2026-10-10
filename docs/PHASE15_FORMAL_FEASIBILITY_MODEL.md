# Formal Context-Conditioned Path Feasibility Model
## ARF-RT Research Extension — Phase 15 Definition

**Branch:** `temporal-context-dev`
**Workspace:** ARF-RT-TEMPORAL
**Status:** Formal Definition (Pre-Implementation)

This document establishes the mathematically precise context-conditioned path feasibility model. It formulates path validation strictly as a Constraint-Satisfaction Problem (CSP).

---

## 1. State Definitions

The state of context along a path is decomposed to prevent the false assumption that satisfying a requirement automatically grants that requirement as a persistent property.

### 1.1 RequiredContext(edge)
The logical conjunction of conditions an edge requires for traversal, derived from `properties_json` of linked constraints.
- **Example:** Edge $e$ requires `{"aws:SourceIp": "10.0.0.0/8"}`.

### 1.2 ProducedContext(edge)
The state that traversing an edge genuinely establishes or alters. It does NOT automatically include the `RequiredContext`.
- **Identity Transition:** Assuming a role produces a new `Principal` identity.
- **Tags:** Assuming a role may produce new `aws:PrincipalTag` values.
- **Null Production:** Traversing a network boundary does not "produce" a session tag.

### 1.3 CarriedContext(path_prefix)
The state that is genuinely preserved and carried across transitions by the attacker's execution environment or session.
- **Identity:** Carried until the next AssumeRole.
- **Session Tokens:** Carry `aws:MultiFactorAuthPresent`.

### 1.4 PathConstraintStore(path_prefix)
The CSP formulation. As a path extends, it accumulates constraints governing the required properties of the attacker's execution environment. 
- Let $C(e_i)$ be the required constraints at hop $i$.
- Let $T(e_{i-1} \rightarrow e_i)$ be the transition constraints modeling how context variables evolve across the hop.
- $PathConstraintStore(P_n) = \bigwedge_{i=1}^n C(e_i) \land \bigwedge_{i=2}^n T(e_{i-1} \rightarrow e_i)$.

---

## 2. Feasibility Evaluation

Path feasibility is evaluated by querying the `PathConstraintStore` for satisfiability. Arbitrary fractional probability penalties are strictly forbidden.

- **SAT:** The constraints are satisfiable under the stated assumptions. A sequence of environments and actions exists that satisfies all requirements.
  - *Effect:* The path is physically possible. The Bayesian path score is preserved (Multiplier = `1.0`).
- **UNSAT:** The constraints are demonstrably contradictory (e.g., $IP \in 10.0.0.0/8 \land IP \in 192.168.0.0/16$ under a static-IP transition assumption).
  - *Effect:* The path is physically impossible. The Bayesian path score is zeroed (Multiplier = `0.0`).
- **UNKNOWN:** Insufficient or unsupported information prevents a conclusion (e.g., missing `properties_json`, unparseable condition keys, or partial overlaps lacking domain semantics).
  - *Effect:* Fallback to baseline behavior. Bayesian path score is preserved (Multiplier = `1.0`). We do not eliminate paths without proof of contradiction.

---

## 3. Context Continuity and Scopes

Context variables exhibit different continuity behaviors across the transition $T(e_{i-1} \rightarrow e_i)$:

### 3.1 Request-Scoped (`aws:SourceIp`)
Evaluated on the network origin of the *request*, not the session.
- **Continuity Transition:** Mutable. Changes if the attacker executes the request from a different origin.
- **Static Assumption:** For this model, we introduce an explicit fixture assumption: *The attacker's execution origin is static across the path unless a specific pivot node is modeled.* Under this assumption, $IP(e_{i-1}) = IP(e_i)$.

### 3.2 Session-Scoped (`aws:MultiFactorAuthPresent`)
Evaluated based on the issuance of the temporary credential.
- **Continuity Transition:** Persistent for the lifetime of the STS session. If an edge establishes an MFA-backed session, subsequent hops using that session inherit the MFA presence.

### 3.3 Principal-Scoped (`aws:PrincipalTag`)
Evaluated based on the active identity.
- **Continuity Transition:** Changes across an `sts:AssumeRole` boundary unless explicitly propagated.

### 3.4 Configuration-Scoped (`sts:ExternalId`)
A static trust policy configuration requirement. The trust policy requires the `ExternalId` parameter to match a configured value.
- **Continuity Transition:** The attacker *supplies* the `ExternalId` in the `AssumeRole` request. It is an action parameter, NOT a persistent session property. It does not carry forward to `CarriedContext`.

---

## 4. Source-Data Compatibility and Schema

### 4.1 Baseline Limitations
Inspection of ARF-RT v1.2 baseline fixtures (`rich_scenario.json`) reveals `properties_json` contains limited strings like `{"condition": "sts:ExternalId"}`. The baseline data does NOT contain `aws:SourceIp` subnets or standard IAM condition operators.

### 4.2 Minimal Research Fixture Schema
To evaluate this extension, separate research fixtures MUST be generated utilizing a standardized subset of IAM condition logic:
```json
"properties": {
  "conditions": [
    {
      "key": "aws:SourceIp",
      "operator": "IpAddress",
      "values": ["10.0.0.0/8"]
    }
  ]
}
```
*Contract:* The research extension parses this schema. If the schema is absent, the edge evaluates to UNKNOWN feasibility. Baseline fixtures are preserved unmodified and will universally evaluate to UNKNOWN (fallback to baseline behavior).

---

## 5. Search Admissibility Analysis

The ARF-RT path search (`engine/paths.py`) uses Best-First Search guided by `p_worst_partial_q8`. 

**Implementation Mechanics:**
1. Scores are quantized to `q8` (0-255).
2. The search orders the priority queue descending by partial path score.
3. As paths extend, the new partial score is the product of previous edge representatives and the new edge representative.

**Admissibility Conditions:**
An upper bound heuristic $H(P)$ is admissible if $H(P) \ge P_{actual}$. Since $P \le 1.0$, extending a path monotonically decreases (or maintains) the true probability. 

Applying the CSP compatibility factor $F \in \{0.0, 1.0\}$:
- If SAT/UNKNOWN: $P_{new} = P_{old} \times 1.0$. The bound is maintained.
- If UNSAT: $P_{new} = P_{old} \times 0.0 = 0$. The bound is tight.

*Conditional Proof:* Assuming the underlying constraint-ID correlation calculation remains monotonic and `q8` rounding errors are floored/bounded correctly as per the baseline implementation, the $\{0.0, 1.0\}$ compatibility multiplier preserves the admissibility of the search queue ordering.

---

## 6. Evaluation Contract and Counterexamples

The model MUST be evaluated deterministically against the following counterexamples.

### CE1: Satisfiable Shared-Context Requirements
- **Setup:** $E_1$ requires `aws:SourceIp = 10.0.0.0/8`. $E_2$ requires `aws:SourceIp = 10.0.0.0/8`.
- **Assumption:** Static execution origin.
- **Result:** SAT. Both constraints are simultaneously satisfiable by an attacker IP of `10.0.0.1`.
- **Path Scoring:** Multiplier `1.0`. Baseline probability preserved.
- **Falsification:** If the model eliminates this path, the implementation of SAT logic is flawed.

### CE2: Contradictory Requirements
- **Setup:** $E_1$ requires `10.0.0.0/8`. $E_2$ requires `192.168.0.0/16`.
- **Assumption:** Static execution origin.
- **Result:** UNSAT. $10.0.0.0/8 \cap 192.168.0.0/16 = \emptyset$.
- **Path Scoring:** Multiplier `0.0`. Path eliminated.
- **Falsification:** If the model assigns a positive probability, the CSP failed to detect the contradiction.

### CE3: Context-Changing Transition
- **Setup:** $E_1$ (AssumeRole). $E_2$ (Action). $E_2$ requires `aws:PrincipalTag/env = prod`. $E_1$ produces identity lacking this tag.
- **Result:** UNSAT (if strict) or UNKNOWN (if model assumes tags might exist but are untracked).
- **Falsification:** Confirms the model correctly scopes Identity across AssumeRole boundaries.

### CE4: Configuration-Scoped Requirement (ExternalId)
- **Setup:** $E_1$ requires `sts:ExternalId = A`. $E_2$ requires `sts:ExternalId = B`.
- **Result:** SAT (or UNKNOWN). `ExternalId` is a request parameter, not carried state. The attacker can supply `A` for $E_1$ and `B` for $E_2$. They do not contradict.
- **Falsification:** If the model treats `ExternalId` as a session variable and returns UNSAT, the scope logic is flawed.

### CE5: Missing/Unsupported Metadata (Baseline Preservation)
- **Setup:** Run against `primary_realistic_scenario.json`.
- **Result:** UNKNOWN for all context checks.
- **Path Scoring:** Multiplier `1.0` universally.
- **Falsification:** Any change in path rankings or scores compared to the original baseline execution mathematically invalidates the fallback guarantee.

---

## 7. Unresolved Questions and Implementation Blockers

1. **CSP Solver Integration:** Implementing a full CSP solver (like Z3) may be overkill and introduce severe runtime overhead during Best-First Search. *Implementation Decision Needed:* Build a lightweight, specialized intersection checker for IPs/Booleans, or integrate a formal solver.
2. **Quantization Thresholds:** A `0.0` multiplier yields `0` in `q8`. Ensure the queue pruning logic correctly discards `0` score paths to avoid infinite loops.
