# CCPF FORMAL DESIGN GATE
## Context-Conditioned Path Feasibility for Probabilistic Cloud Identity Attack-Path Analysis

**Document Status:** Formal Design Specification & Pre-Implementation Gate  
**Target Workspace:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`  
**Target Branch:** `temporal-context-dev`  
**Date:** 2026-10-11  
**Author:** Senior Research Agent & Skeptical Academic Reviewer  
**Engineering Authorization Status:** **GATED (IMPLEMENTATION BLOCKED)**  

> **Evidence & Confidence Legend**
> - **[VERIFIED]**: Directly verified from repository source code, schema, or executable test output.
> - **[INFERRED]**: Formally derived or logically necessary consequence of verified baseline behavior.
> - **[OPEN]**: Unresolved hypothesis, design decision, or uncompleted formal proof obligation.
> - **[BLOCKER]**: Unresolved correctness issue that strictly halts engine modification.

---

## 1. Problem Definition

### 1.1 The Cloud Identity Attack-Path Feasibility Gap
Existing probabilistic cloud identity attack-graph analyzers—including the baseline ARF-RT v1.2 artifact—model edge traversals primarily through Bayesian probability updates, correlation-aware confidence intervals, and structural graph reachability. In this paradigm, an attack path $P = \langle e_1, e_2, \dots, e_n \rangle$ is assigned a joint success probability:
$$p(P) = \prod_{g \in \text{Groups}(P)} p(g)$$
where $g$ represents an equivalence class of correlated edges under a Union-Find partition.

However, real-world cloud identity systems (specifically AWS IAM, Azure AD/Entra ID, and GCP IAM) enforce **multi-dimensional, context-conditioned access control policies** across sequential hops:
1. **Network origin restrictions:** e.g., `aws:SourceIp` within CIDR blocks.
2. **Session authentication state:** e.g., `aws:MultiFactorAuthPresent == true`.
3. **Session duration and validity:** e.g., temporary credentials expiring within bounded windows.
4. **Principal attributes and session tags:** e.g., `aws:PrincipalTag/Department` evaluated against resource tags.
5. **Action parameters vs. ambient state:** e.g., `sts:ExternalId` passed as an input argument during role assumption versus ambient session properties.

### 1.2 The Infeasibility Blindspot in Purely Probabilistic Ranking
In the baseline model, edge probabilities $p(e_i)$ are derived from historical observations, evidence counts, or subjective logic priors. Crucially, the baseline treats each edge traversal as structurally independent with respect to execution context. Consequently, ARF-RT will happily discover, rank, and elevate attack paths that are **physically and logically impossible** in execution. For example:
- **Hop 1:** Traversal requires `aws:SourceIp` $\in 10.0.0.0/8$ (corporate VPC).
- **Hop 2:** Traversal requires `aws:SourceIp` $\in 192.168.1.0/24$ (branch office VPC).

If the attacker operates from a static network position, no single execution environment can satisfy $10.0.0.0/8 \cap 192.168.1.0/24 = \emptyset$. Under the baseline engine, this path receives a positive joint probability $p(P) > 0$ and may even appear in the Top-$K$ attack paths presented to security operators.

### 1.3 The CCPF Research Objective
The objective of **Context-Conditioned Path Feasibility (CCPF)** is to integrate a formal, sound path-feasibility layer with ARF-RT's existing Best-First Search without:
1. Perturbing baseline probability calculations for unconstrained or baseline scenarios.
2. Conflating logical unsatisfiability (UNSAT) with fixed-point probability underflow ($p_{\text{worst}} = 0$).
3. Introducing unsound heuristic pruning that violates Top-$K$ optimality.
4. Conflating unsupported or missing metadata with proof of infeasibility.

---

## 2. Existing Baseline Behavior

### 2.1 Edge Data Model and Constraints Ingestion [VERIFIED]
In `arf_rt/models/core.py` and `arf_rt/adapters/seed_json.py`:
- Scenarios ingest a set of `NodeInput`, `EdgeInput`, and `ConstraintInput` models.
- An edge $e$ contains `edge_id`, `src_node_id`, `dst_node_id`, `edge_type`, `properties_json`, and `is_directed`.
- Constraints are ingested via `ConstraintInput(constraint_id, constraint_type, src_node_id, dst_node_id, properties_json, ...)`.
- In `arf_rt/engine/correlation.py`, constraints are linked to edges to compute evidence bounds ($N$ distinct edges, $M$ distinct source nodes) and to partition edges into correlation components using Union-Find (`DisjointSet`).

### 2.2 Absence of Context Propagation [VERIFIED]
Inspection of `arf_rt/engine/paths.py` (lines 112–208) reveals:
- The search state is a 5-tuple:
  $$\text{State} = (cur\_node, visited, edge\_list, pw\_q8, pb\_q8, worst\_sigs, best\_sigs)$$
- **Zero context awareness:** The state carries no information regarding attacker origin IP, session tokens, assumed role tags, MFA state, or request parameters.
- **Pure structural traversal:** Edge expansion from $cur\_node$ to $dst$ verifies only that $dst \notin visited$ (cycle prevention) and $plen < max\_depth$.
- **Edge properties ignored:** The contents of `properties_json` on edges or constraints are completely ignored during graph traversal in `paths.py`.

### 2.3 Existing Best-First Search and Scoring Mechanics [VERIFIED]
- **Priority Queue:** Built using Python's `heapq` (min-heap).
- **Ordering Key:** `(-p_worst_q8, plen, edge_seq_str, cur_node, visited, edge_list, ...)`
- **Monotonicity:** As paths extend, $pw\_q8$ is updated via `grouped_product_q8(pw_q8, ep) = (pw_q8 * ep) // Q8`. Because $ep \le Q8$, $pw\_q8$ is monotonically non-increasing.
- **Stopping Condition:** Terminates when the heap is empty or when `len(results) == k` paths reaching $target\_nodes$ have been popped.

---

## 3. Scope-Aware Context Model

To model IAM conditions soundly, context variables must not be treated as a monolithic key-value bag. Instead, variables are categorized into four distinct formal scopes with well-defined lifecycles.

```
+-------------------------------------------------------------------------+
|                              CONTEXT SCOPES                             |
+-------------------------------------------------------------------------+
| 1. Request Scope (R)      | Per-hop network/call origin                 |
|                           | e.g., aws:SourceIp, aws:CurrentTime         |
+---------------------------+---------------------------------------------+
| 2. Session Scope (S)      | Carried across session until expiration/swap|
|                           | e.g., aws:MultiFactorAuthPresent            |
+---------------------------+---------------------------------------------+
| 3. Principal Scope (P)    | Tied to active identity; reset at AssumeRole|
|                           | e.g., aws:PrincipalTag/Department           |
+---------------------------+---------------------------------------------+
| 4. Policy/Config Scope (C)| Static requirement / Action input parameter |
|                           | e.g., sts:ExternalId                        |
+-------------------------------------------------------------------------+
```

### 3.1 Request-Scoped Context ($\mathcal{R}$)
- **Semantics:** Properties inherent to the individual API call or network packet.
- **Examples:** `aws:SourceIp`, `aws:CurrentTime`, `aws:UserAgent`.
- **Continuity Rule:** In general cloud operation, an attacker can issue separate API requests from different IP addresses (e.g., via proxies or multiple attacker hosts).
- **Static Origin Assumption [EXPLICIT FIXTURE SPECIFICATION]:** In CE1 and CE2, a scenario-level assumption is explicitly declared: *The attacker operates from a single, static network origin across all sequential steps of the kill-chain.* Under this explicit assumption, $\forall i, j: \mathcal{R}_i(\text{aws:SourceIp}) = \mathcal{R}_j(\text{aws:SourceIp})$. Without this declared assumption, request-scoped IPs across hops are independent free variables.

### 3.2 Session-Scoped Context ($\mathcal{S}$)
- **Semantics:** Properties established when a set of temporary security credentials (STS token) is minted.
- **Examples:** `aws:MultiFactorAuthPresent`, session duration ceiling, session issuer ARN.
- **Continuity Rule:** Persists across all actions executed using the same temporary credential set. When a subsequent hop performs an identity transition (e.g., assumes another role), a *new* session context $\mathcal{S}'$ is minted, and properties of $\mathcal{S}$ do not carry over unless explicitly propagated by AWS STS chaining rules.

### 3.3 Principal-Scoped Context ($\mathcal{P}$)
- **Semantics:** Attributes associated with the active identity entity (IAM User, IAM Role).
- **Examples:** `aws:PrincipalArn`, `aws:PrincipalTag/<key>`, `aws:PrincipalType`.
- **Continuity Rule:** When an edge represents an identity assumption (`sts:AssumeRole`), the principal context **resets**. The post-transition principal attributes are governed by the assumed role's configuration and trust policy, NOT the caller's principal tags (unless session tagging permissions allow passing tags).

### 3.4 Configuration/Parameter Scope ($\mathcal{C}$)
- **Semantics:** Static policy requirements or caller-supplied operation parameters.
- **Example:** `sts:ExternalId`.
- **Critical Distinction [VERIFIED]:** `sts:ExternalId` is a condition evaluated by the target role's trust policy against the `ExternalId` parameter supplied in the `AssumeRole` request payload. It is **not** a persistent credential or carried session token.
- **Non-Interference:** If hop 1 requires `sts:ExternalId == "ClientA"` to assume Role A, and hop 2 requires `sts:ExternalId == "ClientB"` to assume Role B, the attacker simply supplies `"ClientA"` in request 1 and `"ClientB"` in request 2. These constraints operate in separate parameter scopes and **never contradict**.

---

## 4. Transition Transformation Rules

Let a path prefix of length $m$ be $P_m = \langle e_1, e_2, \dots, e_m \rangle$. Each hop $e_i = (u_i, v_i)$ induces a state transition:
$$\Sigma_i = \tau(\Sigma_{i-1}, e_i)$$
where $\Sigma = (\mathcal{R}, \mathcal{S}, \mathcal{P}, \mathcal{C})$ is the typed context tuple.

### 4.1 Transition Taxonomy

| Edge Type / Action | Request Scope $\mathcal{R}$ | Session Scope $\mathcal{S}$ | Principal Scope $\mathcal{P}$ | Config Scope $\mathcal{C}$ |
|---|---|---|---|---|
| **Standard Action** (e.g., S3 read, EC2 launch) | Preserved under static origin; else fresh | Carried | Carried | Consumed per hop |
| **Identity Pivot** (`sts:AssumeRole`) | Preserved under static origin; else fresh | Reset ($\mathcal{S}_{new}$) | Reset ($\mathcal{P}_{new}$) | Consumed; parameter bound |
| **Network Pivot** (e.g., SSM into EC2) | Transformed to Target Host IP | Reset/Preserved | Preserved/Host Role | N/A |
| **Unannotated Edge** (Baseline) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

### 4.2 Mathematical Transformation Functions

For transition $e_{i-1} \to e_i$:
1. **Required Context $\text{Req}(e_i)$:** The predicate over $\Sigma_i$ required for edge traversal:
   $$\text{Req}(e_i) \equiv \bigwedge_{c \in \text{Cond}(e_i)} \text{Eval}(c, \Sigma_i)$$
2. **Produced Context $\text{Prod}(e_i)$:** Explicit state modifications produced by successful traversal. E.g., for `AssumeRole(TargetRole)`:
   $$\text{Prod}(e_i) \equiv (\mathcal{P}_i = \text{Attributes}(\text{TargetRole})) \land (\mathcal{S}_i = \text{NewSession}(\text{TargetRole}))$$
3. **Carried Context $\text{Carried}(e_{i-1} \to e_i)$:**
   $$\text{Frame}(\Sigma_{i-1}, \Sigma_i, e_i) \equiv \bigwedge_{k \notin \text{Invalidated}(e_i)} (\Sigma_i[k] = \Sigma_{i-1}[k])$$

---

## 5. Path Constraint-Store Model

### 5.1 Constraint Store Formalism
Along a path $P_n = \langle e_1, \dots, e_n \rangle$, the **Path Constraint Store** $\Phi(P_n)$ is a first-order logic formula over context variables indexed by step $i$:
$$\Phi(P_n) = \bigwedge_{i=1}^n \text{Req}(e_i, \Sigma_i) \land \bigwedge_{i=2}^n \text{Trans}(e_{i-1}, e_i, \Sigma_{i-1}, \Sigma_i)$$

### 5.2 Incremental Conjunction Property
As a path extends by edge $e_{n+1}$:
$$\Phi(P_{n+1}) = \Phi(P_n) \land \text{Trans}(e_n, e_{n+1}, \Sigma_n, \Sigma_{n+1}) \land \text{Req}(e_{n+1}, \Sigma_{n+1})$$

Because extending a path only **adds conjuncts** to $\Phi$, the constraint store exhibits **monotonic accumulation**:
$$\text{Models}(\Phi(P_{n+1})) \subseteq \text{Models}(\Phi(P_n))$$

---

## 6. SAT / UNSAT / UNKNOWN Semantics

The feasibility evaluation function $\text{EvalFeasibility}(\Phi(P))$ maps a constraint store to a ternary outcome in $\{\text{SAT}, \text{UNSAT}, \text{UNKNOWN}\}$:

```
                  +---------------------------+
                  |  Query Constraint Store   |
                  |          Phi(P)           |
                  +-------------+-------------+
                                |
         +----------------------+----------------------+
         |                                             |
   Sound Proof of                                Unsupported Key,
    Contradiction                               Missing Metadata,
         |                                      or Free Variables
         v                                             |
     +-------+                                         v
     | UNSAT |                                    +---------+
     +-------+                                    | UNKNOWN |
         |                                        +---------+
   Prune Partial                                       |
    Path from                                    Retain Path;
   Priority Queue                                Preserve ARF-RT
   (Score = 0)                                   Bayesian Score
```

### 6.1 Strict Mathematical Definitions
1. **SAT:**
   $$\exists \sigma \in \mathcal{D}_{\Sigma} : \sigma \models \Phi(P)$$
   A concrete assignment of environment attributes (IPs, session states, principal tags) exists that satisfies all conjunctions along the path.
   - *Search Effect:* Feasibility factor $F = 1$. Path expansion continues normally.

2. **UNSAT:**
   $$\neg \exists \sigma \in \mathcal{D}_{\Sigma} : \sigma \models \Phi(P) \iff \Phi(P) \vdash \bot$$
   A sound reasoning procedure proves that the accumulated constraints are mutually contradictory.
   - *Search Effect:* Feasibility factor $F = 0$. The path is physically impossible and **pruned immediately**.

3. **UNKNOWN:**
   The reasoning procedure cannot soundly establish SAT or UNSAT due to:
   - Missing `properties_json` or sidecar context.
   - Unsupported condition operators (e.g., regex patterns, complex date math).
   - Free variables with unbounded external degrees of freedom.
   - *Search Effect:* **Fallback to baseline.** Feasibility factor $F = 1$. The path is **NOT pruned**. Its Bayesian probability ordering is strictly preserved.

### 6.2 UNSAT-Prefix Pruning Analysis and Conditional Theorem

In evaluating whether an UNSAT prefix can soundly authorize branch pruning during Best-First Search, we explicitly separate four distinct mathematical and engineering claims:

1. **Claim 1: Logical Monotonicity of Conjunction (Pure FOL Property):**
   In propositional and first-order logic, conjunction is monotonic:
   $$\forall \Phi_1, \Psi: \quad \Phi_1 \vdash \bot \implies (\Phi_1 \land \Psi) \vdash \bot$$
   Adding conjuncts to an inconsistent formula never restores satisfiability.

2. **Claim 2: Soundness of the Path-Transition Model:**
   Does the physical execution of an attack path $P_{m+k} = P_m \circ \langle e_{m+1}, \dots, e_{m+k} \rangle$ correspond to a monotonic conjunction $\Phi(P_m) \land \Psi$?
   - **Historical Constraints Retained:** Path traversal is strictly causal and sequential. An attacker cannot reach execution step $m+1$ unless every preceding action $e_1, \dots, e_m$ was physically and logically feasible. Therefore, constraints from earlier hops remain binding on the historical execution trajectory.
   - **Step-Indexed Variable Scoping:** Variables must be formally step-indexed (e.g., $\mathcal{R}_i, \mathcal{S}_i, \mathcal{P}_i$) or entity-bound. Distinct physical values must not be collapsed into shared variable symbols unless an explicit continuity rule or scenario assumption mandates identity.
   - **Request-Scoped Variables:** By default, independent cloud API calls represent independent requests. An attacker can invoke separate actions from distinct source IPs unless constrained by a network pivot. Only under an **explicit scenario assumption** (such as the "Static Origin Assumption" $\mathcal{R}_i(\text{IP}) = \mathcal{R}_j(\text{IP})$ in CE1/CE2) do request-scoped IP variables become unified.
   - **Session-Scoped Variables:** Persist across requests utilizing the same temporary credential set. When an identity transition mints a new session, session attributes reset, and expired credentials cannot be reused.
   - **Principal-Scoped Variables:** Reset across `sts:AssumeRole` boundaries. Post-transition principal attributes are governed by the assumed role's entity attributes, not the caller's tags, unless session tagging is authorized.
   - **Configuration vs. Input Parameters:** Action parameters (such as `sts:ExternalId` supplied to `AssumeRole`) are consumed per hop and do not carry forward or contradict external IDs in subsequent hops.
   - **No Retroactive Invalidation:** A transition transformation $T(e_{m-1} \to e_m)$ does not discard or rewrite the constraints that governed earlier steps; it only defines the boundary conditions and frame relations for subsequent steps.

3. **Claim 3: Soundness of UNSAT-Prefix Pruning in the Implementation:**
   Even if Claims 1 and 2 hold mathematically, the software implementation must guarantee that:
   - Incremental constraint-store operations do not mutate earlier prefix representations.
   - The constraint solver never produces an UNSAT verdict due to internal state corruption, variable name shadowing, or parser errors.
   - UNKNOWN is never treated as UNSAT.

4. **Claim 4: Completeness and Admissibility of the Top-$K$ Search:**
   Pruning an UNSAT prefix does not eliminate any physically feasible path only if the solver procedure is sound. Top-$K$ completeness further requires that no feasible path with $p \ge p(k\text{-th})$ is bypassed and that integer-floor underflow ($p_{\text{worst\_q8}} = 0$) is never conflated with UNSAT.

**CRITICAL FORMAL STATUS:**
> **Theorem Status:** **CONDITIONAL — preservation of historical constraints and scope semantics must be proved.**  
> Proving logical monotonicity of conjunction (Claim 1) does **NOT** automatically prove the physical soundness of the path-transition model (Claim 2), implementation soundness (Claim 3), or Top-$K$ completeness (Claim 4). The pruning theorem is valid if and only if Claims 1–3 are fully established by verified implementation contracts.

---

## 7. Solver Assumptions and Supported Logic

### 7.1 Architecture: Restricted Lightweight Solver vs. External SMT
During the pre-implementation audit, adding heavyweight external solver dependencies (such as Z3, CVC5, or MiniZinc) was evaluated.
**Decision: Restricted Deterministic Constraint Evaluator (RDCE).**
- *Rationale:* Heavyweight SMT solvers introduce non-negligible process/FFI overhead during high-frequency Best-First Search expansions, non-deterministic solver timeouts, and binary packaging hazards on Windows platforms.
- *RDCE Design:* A domain-restricted, sound, zero-dependency Python constraint evaluator that operates strictly over a decidable subset of IAM condition logic.

### 7.2 Soundness vs. Completeness Contract
- **Soundness (Mandatory):**
  $$\text{RDCE}(\Phi) = \text{UNSAT} \implies \Phi \vdash \bot$$
  Every contradiction detected by RDCE must be a mathematically indisputable contradiction under the declared model. False UNSAT classifications are strictly unacceptable, as they would prune feasible attack paths.
- **Incompleteness (Permitted & Conservative):**
  $$\Phi \vdash \bot \;\not\implies\; \text{RDCE}(\Phi) = \text{UNSAT}$$
  Because RDCE only reasons over the Safe Fragment, complex or unmodeled constraints (e.g., cross-field regex, arithmetic conditions) will yield $\text{UNKNOWN}$. Incompleteness is conservative: returning $\text{UNKNOWN}$ preserves the path in the search frontier and retains baseline Bayesian scoring.

### 7.3 Supported Logic Subset (The "Safe Fragment")
The RDCE supports:
1. **CIDR Network Membership (`IpAddress` / `NotIpAddress`):**
   - Domain: IPv4 and IPv6 addresses.
   - Semantics: Subnet containment and disjointness via Python standard library `ipaddress`.
   - Decision Procedure: Interval disjointness testing. $S_1 \cap S_2 = \emptyset \implies \text{UNSAT}$.
2. **Boolean Identity (`Bool`):**
   - Domain: `aws:MultiFactorAuthPresent` $\in \{\text{true}, \text{false}\}$.
   - Decision Procedure: Truth value clash. $(\text{true} \land \text{false}) \implies \text{UNSAT}$.
3. **Exact String Equality / Set Membership (`StringEquals` / `StringLike` without wildcards):**
   - Domain: Principal tags, external IDs, account IDs.
   - Decision Procedure: Value equality. $(x = v_1) \land (x = v_2)$ where $v_1 \ne v_2 \implies \text{UNSAT}$.

### 7.4 Soundness Contract for Unsupported Operators and Edge Cases
1. **Unsupported Keys/Operators:** If an edge constraint contains any operator or key outside the Safe Fragment (e.g., `NumericLessThan`, `DateGreaterThan`, wildcards `*`, complex ARN conditions), the evaluator **MUST immediately return UNKNOWN**.
2. **Missing Metadata:** If `properties_json` is missing or contains unparseable JSON, the evaluator **MUST return UNKNOWN**.
3. **Timeouts / Execution Interrupts:** Any solver timeout or unhandled exception **MUST default to UNKNOWN**.
4. **Strict Isolation from Probability:** A zero Q8 probability score ($p_{\text{worst\_q8}} = 0$) resulting from integer division underflow **MUST NEVER** act as an UNSAT signal. Feasibility evaluation is strictly binary/ternary and decoupled from probability scores. No arbitrary fractional penalties or multipliers (e.g., $0.5$) are permitted.

---

## 8. Q8 Numerical Representation vs. CSP Semantics

### 8.1 ARF-RT Fixed-Point Arithmetic [VERIFIED]
In `arf_rt/config.py` line 11:
```python
Q8: int = 100_000_000  # 10^8 scaling factor
```
In `arf_rt/util/canon.py` lines 217–240:
```python
def edge_p_q8(alpha_i: int, beta_i: int) -> int:
    return (alpha_i * Q8) // (alpha_i + beta_i)

def grouped_product_q8(p_q8: int, edge_p_q8_val: int) -> int:
    return (p_q8 * edge_p_q8_val) // Q8
```

### 8.2 The Critical Underflow Hazard
Because ARF-RT performs integer division (`//`), precision underflow can occur:
- If a path contains multiple low-probability edges (e.g., $p_1 = 0.0001 \implies 10,000$ in Q8), chaining several such hops can yield:
  $$p_{\text{worst\_q8}} = (10,000 \times 5,000) // 100,000,000 = 0$$
- In pure ARF-RT, a path with $p_{\text{worst\_q8}} = 0$ is a valid probabilistic path whose probability has floored to zero in 8-decimal fixed-point precision.
- **CRITICAL REQUIREMENT:** A Q8 score of $0$ **MUST NEVER** be interpreted as a CSP $\text{UNSAT}$ signal.
- Infeasibility is a **logical property** ($F \in \{0, 1\}$ or status $\in \{\text{SAT}, \text{UNSAT}, \text{UNKNOWN}\}$), entirely orthogonal to numerical probability.
- Probability values are never multiplied by fractional penalty heuristics (e.g., $0.5$ or $0.1$). Feasibility acts solely as a binary filter $\{0, 1\}$.

---

## 9. CE1–CE6 Formula-Level Analysis

The counterexample fixture suite in `tests/fixtures/research_context_feasibility/` defines six fundamental research scenarios. Here we present the complete mathematical formalization for each scenario.

### 9.1 CE1: Compatible Persistent Context
- **Fixture Files:** `ce1_compatible_persistent.scenario.json`, `ce1_compatible_persistent.context.json`
- **Variables:** $\mathcal{R}_1(\text{aws:SourceIp}), \mathcal{R}_2(\text{aws:SourceIp}) \in \text{IPv4}$
- **Initial Condition:** Static origin assumption declared: $\mathcal{R}_1(\text{aws:SourceIp}) = \mathcal{R}_2(\text{aws:SourceIp}) = IP_{\text{origin}}$.
- **Edge 1 Requirement:** $IP_{\text{origin}} \in 10.0.0.0/8$
- **Edge 2 Requirement:** $IP_{\text{origin}} \in 10.1.0.0/16$
- **Formula:** $\Phi(\text{CE1}) \equiv (IP_{\text{origin}} \in 10.0.0.0/8) \land (IP_{\text{origin}} \in 10.1.0.0/16)$
- **Intersection:** $10.0.0.0/8 \cap 10.1.0.0/16 = 10.1.0.0/16 \ne \emptyset$.
- **Expected Outcome:** **SAT**
- **Score Effect:** Multiplier = 1.0 (Probability PRESERVED).
- **Required Solver Capability:** IPv4 CIDR intersection non-emptiness check.

### 9.2 CE2: Contradictory Persistent Context
- **Fixture Files:** `ce2_contradictory_persistent.scenario.json`, `ce2_contradictory_persistent.context.json`
- **Variables:** $\mathcal{R}_1(\text{aws:SourceIp}), \mathcal{R}_2(\text{aws:SourceIp}) \in \text{IPv4}$
- **Initial Condition:** Static origin assumption declared: $\mathcal{R}_1(\text{aws:SourceIp}) = \mathcal{R}_2(\text{aws:SourceIp}) = IP_{\text{origin}}$.
- **Edge 1 Requirement:** $IP_{\text{origin}} \in 10.0.0.0/8$
- **Edge 2 Requirement:** $IP_{\text{origin}} \in 192.168.0.0/16$
- **Formula:** $\Phi(\text{CE2}) \equiv (IP_{\text{origin}} \in 10.0.0.0/8) \land (IP_{\text{origin}} \in 192.168.0.0/16)$
- **Intersection:** $10.0.0.0/8 \cap 192.168.0.0/16 = \emptyset \implies \bot$.
- **Expected Outcome:** **UNSAT**
- **Score Effect:** Multiplier = 0.0 (Path ELIMINATED / Pruned).
- **Required Solver Capability:** IPv4 CIDR disjointness detection.

### 9.3 CE3: Context-Changing Transition Permitted
- **Fixture Files:** `ce3_transition_permitted.scenario.json`, `ce3_transition_permitted.context.json`
- **Variables:** Hop 1 uses $\mathcal{R}_1(\text{aws:SourceIp})$; Hop 2 represents a pivot through an EC2 instance / bastion host.
- **Edge 1 (Caller to Bastion):** $IP_{\text{attacker}} \in 203.0.113.0/24$ (external public IP).
- **Transition Rule:** Traversing Edge 1 pivots execution onto Bastion host; Hop 2 outbound request originates from Bastion internal IP $\mathcal{R}_2(\text{aws:SourceIp}) = IP_{\text{bastion}} = 10.0.1.50$.
- **Edge 2 Requirement:** $\mathcal{R}_2(\text{aws:SourceIp}) \in 10.0.0.0/16$.
- **Formula:** $\Phi(\text{CE3}) \equiv (IP_{\text{attacker}} \in 203.0.113.0/24) \land (IP_{\text{bastion}} = 10.0.1.50) \land (IP_{\text{bastion}} \in 10.0.0.0/16)$.
- **Analysis:** Because the transition models network transformation ($\mathcal{R}_2 \ne \mathcal{R}_1$), there is no contradiction between external attacker IP and internal VPC IP.
- **Expected Outcome:** **SAT**
- **Score Effect:** Multiplier = 1.0 (Probability PRESERVED).
- **Required Solver Capability:** Variable scoping and network pivot transformation mapping.

### 9.4 CE4: Missing or Unsupported Context Metadata
- **Fixture Files:** `ce4_unsupported_metadata.scenario.json`, `ce4_unsupported_metadata.context.json`
- **Setup:** Edge constraints specify unrecognized condition keys or unsupported operators (e.g., custom regex or missing sidecar properties).
- **Formula:** $\Phi(\text{CE4}) \equiv \text{Req}(e_1) \land \text{Unsupported}(e_2)$.
- **Analysis:** The evaluator cannot prove SAT (cannot verify unsupported operator) and cannot soundly prove UNSAT (lack of contradiction).
- **Expected Outcome:** **UNKNOWN**
- **Score Effect:** Multiplier = 1.0 (Fallback to Baseline; PRESERVED).
- **Required Solver Capability:** Graceful exception trap yielding `UNKNOWN` without exception or falsification.

### 9.5 CE5: Baseline Compatibility (Non-Perturbation)
- **Fixture Files:** `ce5_baseline_compatibility.context.json` referencing `diamond_scenario.json` and `primary_realistic_scenario.json`.
- **Setup:** Standard ARF-RT v1.2 scenario files without any research context sidecar annotations.
- **Formula:** $\Phi(\text{CE5}) = \emptyset$ (no context constraints).
- **Analysis:** All edges evaluate to `UNKNOWN` context constraints.
- **Expected Outcome:** **UNKNOWN** universally.
- **Score Effect:** Multiplier = 1.0 (STRICT IDENTITY with baseline top-$K$ rankings and exact Q8 scores).
- **Required Solver Capability:** Baseline pass-through mode.

### 9.6 CE6: Principal Scope Boundary Across AssumeRole
- **Fixture Files:** `ce6_principal_scope_boundary.scenario.json`, `ce6_principal_scope_boundary.context.json`
- **Variables:** $\mathcal{P}_1$ (Caller Principal), $\mathcal{P}_2$ (Assumed Role Principal).
- **Hop 1 (`sts:AssumeRole`):** `DevUser` assumes `AppDevRole`.
  - Trust policy strictly enforces: `Null(aws:RequestTag/Department) == true` (forbids passing session tags).
  - Produced context: Role static attached tag `aws:PrincipalTag/Department = "ApplicationDevelopment"`.
- **Hop 2 (`secretsmanager:GetSecretValue`):** Access to `ProductionMasterKey`.
  - Required context: `aws:PrincipalTag/Department == "SecurityOperations"`.
- **Transition Rule:** AssumeRole resets principal scope. In the absence of session tag assertion, $\mathcal{P}_2(\text{Department}) = \text{Tags}(\text{AppDevRole})[\text{"Department"}] = \text{"ApplicationDevelopment"}$.
- **Formula:** $\Phi(\text{CE6}) \equiv (\mathcal{P}_2(\text{Department}) = \text{"ApplicationDevelopment"}) \land (\mathcal{P}_2(\text{Department}) = \text{"SecurityOperations"}) \implies \bot$.
- **Expected Outcome:** **UNSAT**
- **Score Effect:** Multiplier = 0.0 (Path ELIMINATED / Pruned).
- **Critical Dependency on Explicit Assumptions [VERIFIED LIMITATION]:**
  The UNSAT outcome of CE6 is **not** an unconditional law of AWS IAM role assumption. It strictly depends on four explicit, scenario-specific constraints:
  1. The caller (`DevUser`) is denied or lacks `sts:TagSession` authorization.
  2. The target role (`AppDevRole`) trust policy strictly requires `Null(aws:RequestTag/Department) == true`.
  3. The target role has a static, immutable tag `Department = ApplicationDevelopment`.
  4. No transitive session tags or tag-inheritance policies are active.
  *Observation:* In real-world AWS environments where trust policies permit session tagging or do not restrict request tags, an authorized caller could supply `Department=SecurityOperations` during the `AssumeRole` request, rendering the path satisfiable. If any of these four constraints are omitted or unmodeled, the sound evaluator outcome would be **UNKNOWN** or SAT, not UNSAT.

### 9.7 Distinct Validation Levels Across CE1–CE6 [VERIFIED]
To avoid conflating data validation with algorithmic correctness, we distinguish four separate validation tiers:
1. **Tier 1 — Schema Ingest Validation:** Verification that scenario JSON conforms to ARF-RT Pydantic models (`ScenarioInput`). *Status: PASSED (6/6)*.
2. **Tier 2 — Graph Topology Consistency:** Verification that sidecar edge sequences match actual graph nodes and edges. *Status: PASSED (6/6)*.
3. **Tier 3 — Hand-Derived Analytical Specifications:** Human-authored formal target outcomes (`manifest.json`). *Status: VERIFIED (Analytical Specifications Only)*.
4. **Tier 4 — Algorithmic Solver Execution:** Computational validation by an active constraint solver. *Status: NOT IMPLEMENTED (No solver has executed in the repository)*.

---

## 10. Baseline Compatibility and Search Invariants

To guarantee that CCPF remains a sound, non-destructive extension of ARF-RT, any candidate engine implementation must preserve the following concrete mathematical and algorithmic invariants:

### 10.1 Mathematical Arithmetic Invariants [VERIFIED in canon.py & config.py]
1. **Edge Probability Calculation:**
   $$\text{edge\_p\_q8}(\alpha_i, \beta_i) = \lfloor (\alpha_i \times Q8) / (\alpha_i + \beta_i) \rfloor$$
   where $Q8 = 100\_000\_000$ ($10^8$). Integer floor division must be preserved without floating-point conversion.
2. **Grouped Product Calculation:**
   $$\text{grouped\_product\_q8}(p_{\text{worst\_q8}}, ep) = \lfloor (p_{\text{worst\_q8}} \times ep) / Q8 \rfloor$$
3. **Correlation-Group Deduplication:**
   Group signatures (`w_sig`, `b_sig`) partition edges via Union-Find. Repeated occurrences of the same group signature along a path must contribute probability $1.0$ (no repeated multiplication).
4. **Underflow Separation:**
   Any path yielding $p_{\text{worst\_q8}} = 0$ via integer underflow must **never** be treated as a CSP UNSAT signal.

### 10.2 Algorithmic Search Invariants [VERIFIED in paths.py]
1. **Heap Priority Ordering:**
   Heap items are ordered by the min-heap tuple:
   $$\text{PriorityKey} = (-p_{\text{worst\_partial\_q8}}, \text{path\_length}, \text{edge\_id\_seq\_str})$$
   Deterministic tie-breaking depends on:
   - Lower path length (shorter paths favored on equal probability).
   - Lexicographic string comparison of canonical edge ID sequences (`COLLATE BINARY`).
2. **Stopping Condition:**
   Search halts when the priority queue is empty or when exactly $K$ paths reaching target nodes have been accumulated.
3. **Conservative Feasibility Pruning:**
   A path prefix $P$ may be pruned if and only if $\text{RDCE}(\Phi(P)) == \text{UNSAT}$.
   If $\text{RDCE}(\Phi(P)) \in \{\text{SAT}, \text{UNKNOWN}\}$, the path must remain on the search frontier, and its heap priority must be exactly $-p_{\text{worst\_partial\_q8}}$.

---

## 11. Search Correctness and Top-K Proof Obligations

Before any code modification in `arf_rt/engine/paths.py` is permitted, the following eight formal proof obligations must be tracked and resolved:

| # | Obligation | Target Guarantee | Current Formal Status |
|---|---|---|---|
| **O1** | **Solver Soundness** | RDCE returns $\text{UNSAT} \implies \Phi(P) \vdash \bot$ | **OPEN** (Requires unit testing over Safe Fragment) |
| **O2** | **Scope Reset Invariance** | Scope transitions correctly reset $\mathcal{P}$ and $\mathcal{S}$ without variable name clashes | **OPEN** (Requires formal transition mapping) |
| **O3** | **Monotonic UNSAT Pruning** | Prefixes proven UNSAT never become SAT upon extension | **CONDITIONAL — preservation of historical constraints and scope semantics must be proved** |
| **O4** | **Score Invariance** | Feasible paths retain exact baseline $p_{\text{worst\_q8}}$ | **OPEN** (Pending integration verification) |
| **O5** | **Tie-Break Preservation** | Relative ordering of equal-score paths is strictly preserved | **OPEN** (Pending integration verification) |
| **O6** | **Search-Bound Admissibility** | Heuristic priority bound remains admissible under feasibility filter | **OPEN** (Formal proof required) |
| **O7** | **Exact Top-$K$ Completeness** | No feasible path with $p \ge p(k\text{-th})$ is missed by pruning | **OPEN** (Formal proof required) |
| **O8** | **Non-Perturbation under UNKNOWN** | Any $\text{UNKNOWN}$ path preserves baseline rank and score | **OPEN** (Pending regression test) |

### Formal Analysis of O6 & O7 (Top-$K$ Completeness Obligations)
While pruning paths that have physical probability $0$ is intuitively attractive, exact Top-$K$ completeness cannot be claimed as unconditionally proven:
- **Heuristic Admissibility (O6):** If the feasibility evaluator ever returns an unsound UNSAT verdict on a path prefix, the entire subtree is pruned, destroying admissibility and completeness.
- **Tie-Break Perturbation (O5):** If feasibility checks alter the expansion order or candidate generation sequence, paths with identical probabilities could reorder.
- **Underflow Interaction (O7):** If a zero-score path ($p_{\text{worst\_q8}} = 0$) reaches a target before positive-score paths (due to depth bounds or queue exhaustion), handling of zero-score feasible paths must not diverge between baseline and CCPF.
Therefore, obligations O6 and O7 remain **OPEN** until formally verified against the real search algorithm.

---

## 12. Threats to Validity

1. **Construct Validity (IAM Semantic Realism):** Real-world AWS IAM evaluation includes condition keys not modeled in the Safe Fragment (e.g., service-specific condition keys, STS transitive tags). Treating these as $\text{UNKNOWN}$ avoids false pruning, but limits pruning efficacy on unmodeled policies.
2. **Internal Validity (Static Origin Assumption):** Assuming a static IP across all steps in CE1/CE2 is an artificial scenario restriction. If an attacker controls multiple IP addresses, an apparent IP contradiction might be circumvented via multi-homed attack orchestration. This assumption must always be explicitly stated in research claims.
3. **External Validity (Benchmark Representation):** The CE1–CE6 fixture suite contains synthetic, controlled topologies designed to test corner cases. Evaluation results on CE1–CE6 cannot be generalized to enterprise-scale environments without empirical validation on large-scale benchmarks.
4. **Reliability (Integer Precision Underflow):** Deep attack paths ($plen > 8$) risk fixed-point underflow in Q8 precision. Testing must verify that deep paths do not cause false interactions between zero Q8 probabilities and constraint feasibility.

---

## 13. Unresolved Design Decisions

1. **Sidecar Format vs. Native Schema Extension:** Should context annotations live in separate `.context.json` sidecar files (as currently structured in CE1–CE6) or be ingested directly into an extended `properties_json` schema in `models/core.py`?  
   *Current Stance:* Retain `.context.json` sidecars during research prototyping to guarantee 100% baseline schema non-perturbation.
2. **Search Hook Point in `paths.py`:** Should feasibility be checked:
   - Option A: At candidate neighbor generation (line 195, before `heappush`)? -> Saves heap memory and avoids pushing doomed branches.
   - Option B: When popping from the heap (line 144, after `heappop`)? -> Computes feasibility only for paths that actually compete for Top-$K$.  
   *Trade-off:* Option A prunes subgraphs earlier; Option B minimizes solver calls if $K$ is small.
3. **Caching Constraint Stores:** Chained path prefixes share constraint stores. A persistent immutable data structure (or prefix memoization table) will prevent redundant constraint parsing.

---

## 14. Explicit Criteria Required Before Engine Implementation Is Authorized

Engine implementation (i.e., modifying `arf_rt/engine/paths.py` or creating `arf_rt/engine/feasibility.py`) is strictly **BLOCKED** until all of the following gates are fulfilled:

- [ ] **Gate 1: Formal Proof Review Complete:** Formal verification of proof obligations O1, O2, O7 by an independent review.
- [ ] **Gate 2: Standalone RDCE Unit Test Suite:** The `Restricted Deterministic Constraint Evaluator` is implemented as an isolated, standalone research prototype in a separate module (e.g., `tests/research/test_rdce.py`) and achieves 100% passing tests across all Safe Fragment operators before any search integration.
- [ ] **Gate 3: Baseline Mirror Protection Check:** Verification that `Artifact/ARF-RT-BASELINE` remains untouched and identical to Git commit `04d2bae`.
- [ ] **Gate 4: Explicit User Authorization:** Formal user confirmation to proceed to Stage C (Engine Prototyping) following review of this Design Gate document.

---

## 15. Summary Verdict

**VERDICT: GO TO ISOLATED PROTOTYPE (FORMAL DESIGN DRAFTED · IMPLEMENTATION GATE REMAINS OPEN)**

The formal design for Context-Conditioned Path Feasibility (CCPF) is logically specified, internally consistent, and clearly scoped. The separation between probability scoring and logical feasibility is mathematically established.

**Formal Status:** Formal design drafted; implementation gate remains open until the required assumptions and proof obligations are verified.  
**Scientific Novelty Classification:** Potential research direction; novelty not established.

All engine code in `arf_rt/` remains untouched. Integration into the search engine remains strictly gated pending isolated evaluator prototyping and explicit authorization.
