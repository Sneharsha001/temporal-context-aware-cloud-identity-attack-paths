# Temporal / Context-Aware Correlated Attack-Path Inference
## Research Design Document — ARF-RT Extension

**Branch:** `temporal-context-dev`
**Baseline:** ARF-RT v1.2 (`arf-rt-v1.2-baseline` tag)
**Status:** Design only. Phase 14.1 Review applied. No implementation performed.
**Source basis:** Direct inspection of ARF-RT v1.2 source code, schema, and baseline fixtures.

---

## Phase 14.1 Review Findings

A rigorous review of the design identified critical data provenance issues and logical flaws in temporal semantics.

### Corrected Claims & Limitations
1. **Data Provenance:** The baseline fixtures (e.g., `rich_scenario.json`) do NOT contain rich IAM condition keys like `aws:SourceIp` or `10.0.0.0/8` in `properties_json`. They contain simplified string markers (e.g., `{"condition": "sts:ExternalId"}`). The proposed extension cannot operate on data that doesn't exist. **Limitation:** Evaluating this research requires defining and generating new research-fixtures with enriched `properties_json` representations.
2. **Temporal Semantics:** The previous design conflated *evidence collection time* (`observed_at`) with *attack execution time*. Two observations collected 24 hours apart do NOT imply the attacker traversed the hops 24 hours apart. Therefore, we cannot declare an `sts:AssumeRole` session "expired" based on the `observed_at` gap. Since actual execution times are unavailable, temporal feasibility is UNKNOWN.
3. **Context Scope:** Context attributes have distinct scopes. `aws:SourceIp` is request-scoped and mutable; `aws:MultiFactorAuthPresent` is session-scoped; `sts:ExternalId` is configuration-scoped. Comparing mutable request-scoped attributes across hops requires the explicit assumption that the attacker's execution environment remains static.

### Remaining Mathematical Questions
- **Probability distributions for partial overlap:** If an attacker is known to be in `10.0.0.0/8`, what is the probability they are in `10.0.1.0/24`? Without empirical data, any fractional probability is arbitrary.

### Revised Scope
Due to the unavailability of attack execution times, **Temporal Feasibility is moved to Future Work**. The smallest defensible contribution is narrowed strictly to:
**Context-Conditioned Path Feasibility (modeled as a Constraint-Satisfaction Problem).**

---

## 1. Research Question

Does formulating operational execution context as a Constraint-Satisfaction Problem (CSP) during path construction successfully suppress logically impossible paths without breaking the admissibility of the Bayesian search bound, compared to a baseline that assumes hops are contextually independent?

---

## 2. Problem Statement

ARF-RT v1.2's path search constructs sequences by multiplying edge probabilities, assuming that traversing hop $N$ guarantees a state from which hop $N+1$ can be traversed. However, AWS IAM conditions (`aws:SourceIp`, `aws:MultiFactorAuthPresent`) impose strict contextual requirements. If an attacker's carried session or request state logically contradicts a hop's requirements, the path is physically impossible, yet the baseline assigns it a positive probability.

---

## 3. Confirmed Baseline Behavior

1. **Correlation:** Groups edges strictly by shared `constraint_id`. `properties_json` is ignored.
2. **Path Construction:** `p_worst(path) = product P(group_rep)`. Context-free and order-independent beyond group deduplication.
3. **Data Schema:** `properties_json` exists but contains only minimal string attributes in standard baseline fixtures.

---

## 4. Specific Limitations of the Existing Approach

- **No context compatibility check:** Paths with mutually exclusive conditions (e.g., conflicting `aws:SourceIp` ranges, assuming a static attacker origin) are treated as fully viable.
- **Untracked State:** The engine does not track what identity, tags, or session properties cross an `sts:AssumeRole` boundary.

---

## 5. Proposed Contribution: Context-Conditioned Path Feasibility

Augment the path construction algorithm to maintain a `CarriedContext` state, formulated as a CSP.

At each hop extension $E_{n-1} \rightarrow E_n$:
1. Evaluate compatibility between `CarriedContext` and `RequiredContext(E_n)`.
2. Apply a strict binary `compatibility_factor` $\in \{0.0, 1.0\}$:
   - **COMPATIBLE / UNKNOWN:** Factor = `1.0`. The baseline Bayesian probability is preserved.
   - **CONFLICTING:** Factor = `0.0`. The path is logically impossible and eliminated.
   - *(Partial overlaps and arbitrary fractions are explicitly rejected to avoid inventing probabilities).*

**M5 (Search Admissibility) Resolved:** 
The best-first search uses `p_worst_partial_q8` as an admissible upper bound. Because the `compatibility_factor` is strictly either $1.0$ (no change) or $0.0$ (eliminated), the partial path score is monotonically non-increasing. Thus, the bound remains strictly admissible.

---

## 6. Scope

**In Scope:**
- Defining a new research-fixture schema to inject rich IAM conditions into `properties_json`.
- Implementing CSP-based context compatibility logic (e.g., disjoint IP subnet evaluation).
- Applying strict $\{0.0, 1.0\}$ feasibility filters to `p_worst` during path search.

**Explicitly Out of Scope (Future Work):**
- Temporal session expiration (requires modeling attack execution time).
- Fractional probabilities for partial context overlap.
- Context-conditioned statistical correlation (Union-Find).
- Parsing raw AWS PMapper dumps (research fixtures will be synthetically enriched).

---

## 7. Counterexamples Required (Revised)

**CE1: Shared keys, same values (Sequential Feasibility)**
- *Fixture:* Path $E1 \rightarrow E2$. E1 requires `aws:SourceIp = 10.0.0.0/8`. E2 requires `aws:SourceIp = 10.0.0.0/8`. (Assuming request-origin is static).
- *Expected:* Path is feasible (`compatibility = 1.0`). Their probabilities multiply independently.

**CE2: Shared keys, conflicting values (Infeasibility)**
- *Fixture:* Path $E1 \rightarrow E2$. E1 requires `10.0.0.0/8`. E2 requires `192.168.0.0/16`. (Assuming request-origin is static).
- *Expected:* Logic conflict. Compatibility evaluates to `0.0`. Path is eliminated. 

**CE5: Baseline Non-Perturbation (Fallback to Baseline)**
- *Fixture:* Original primary realistic fixture (where `properties_json` lacks rich IP/MFA conditions).
- *Expected:* All context evaluations return UNKNOWN. Fallback behavior applies `compatibility = 1.0`. Zero change to original baseline results.

**NO CODE IMPLEMENTATION HAS BEEN PERFORMED.**
