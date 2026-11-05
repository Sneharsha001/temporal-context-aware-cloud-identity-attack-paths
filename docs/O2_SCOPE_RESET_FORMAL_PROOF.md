# O2 — Formal Scope Reset Invariance Proof

**Repository:** `C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL`
**Date:** 2026-10-29
**Branch:** `temporal-context-dev`
**RDCE Implementation:** `research/ccpf/rdce.py` lines 296-335 (carry-over/reset logic)

---

## 1. Theorem Statement

### Theorem O2 (Scope Reset Invariance)

For every transition `e_i → e_{i+1}` in a path prefix, the RDCE's scope binding mechanism correctly implements the formal transition semantics defined in `CCPF_FORMAL_DESIGN_GATE.md` Section 4.

Let `Σ_i = (ℛ_i, 𝒮_i, 𝒫_i, 𝒞_i)` be the context tuple at hop `i`. The transition function `τ(Σ_i, e_{i+1}) = Σ_{i+1}` satisfies:

| Transition Type | ℛ (Request) | 𝒮 (Session) | 𝒫 (Principal) | 𝒞 (Config) |
|-----------------|-------------|-------------|---------------|------------|
| **Standard Action** | Preserved under static origin; else fresh | Carried | Carried | Consumed (fresh) |
| **AssumeRole** | Preserved under static origin; else fresh | **Reset** (fresh) | **Reset**, then initialized from produced `aws:PrincipalTag/*` | Consumed (fresh) |
| **PIVOT_TRANSITION** | Rebound to `network_execution_origin` | Reset/preserved per docs | Preserved/host role | N/A |
| **IDENTITY_DERIVATION** | N/A | N/A | Carried from produced context of `from_hop` | N/A |

**Invariance Property:** After each transition, the active context stores contain exactly the variables that should be in scope according to the formal model, with no variable name clashes or improper carry/retention.

---

## 2. Formal State Machine Model

### 2.1 State Definition

At hop `h`, the evaluator maintains six typed stores:

```
State(h) = (
  AllowedCIDRs: Dict[hop, List[CIDR]],           // ℛ positive
  DeniedCIDRs: Dict[hop, List[CIDR]],            // ℛ negative
  PrincipalStrings: Dict[hop, Dict[Tag, Set[Str]]],  // 𝒫
  SessionStrings: Dict[hop, Dict[Tag, Set[Str]]],    // 𝒮
  ConfigStrings: Dict[hop, Dict[Tag, Set[Str]]],     // 𝒞
  RequestStrings: Dict[hop, Dict[Tag, Set[Str]]],    // ℛ string (non-IP)
  SessionBoolDomains: Dict[hop, Dict[Key, Set[Bool]]], // 𝒮 bool
  NullAssertions: Dict[hop, Dict[Key, Bool]],        // All scopes
  ProducedState: Dict[hop, Dict[Key, Value]]          // Postconditions
)
```

### 2.2 Transition Function

For hop `h > 1`, given `State(h-1)` and transition `e_{h-1} → e_h`:

```python
def transition(prev_state, prev_hop, curr_hop, transitions):
    # Determine if AssumeRole boundary
    is_assume_role = (
        prev_hop.edge_type == "sts:AssumeRole"
        or any(t.from_hop == prev_hop_num and t.to_hop == curr_hop_num 
               and t.relation_type in ("IDENTITY_DERIVATION", "ROLE_ASSUMPTION")
               for t in transitions)
    )
    
    if not is_assume_role:
        # Standard action: carry 𝒫, 𝒮, 𝒮_bool
        PrincipalStrings[h] = copy(PrincipalStrings[h-1])
        SessionStrings[h] = copy(SessionStrings[h-1])
        SessionBoolDomains[h] = copy(SessionBoolDomains[h-1])
        # ℛ, 𝒞 fresh (except static origin handled later)
    else:
        # AssumeRole boundary
        SessionStrings[h] = {}
        SessionBoolDomains[h] = {}
        PrincipalStrings[h] = {}
        # Re-initialize 𝒫 from produced tags of prev_hop
        for p_key, p_val in ProducedState[prev_hop_num].items():
            if p_key.startswith("aws:PrincipalTag/") and isinstance(p_val, str):
                PrincipalStrings[h][p_key] = {p_val}
```

---

## 3. Proof of Scope Reset Invariants

### Lemma 1: Standard Action Carry Invariants

**Statement:** For a standard action transition (not AssumeRole, not PIVOT, not IDENTITY_DERIVATION on the entering hop):
- `PrincipalStrings[h] = PrincipalStrings[h-1]`
- `SessionStrings[h] = SessionStrings[h-1]`
- `SessionBoolDomains[h] = SessionBoolDomains[h-1]`
- `RequestStrings[h] = {}` (fresh, except static origin handled separately)
- `ConfigStrings[h] = {}` (fresh per hop)
- `AllowedCIDRs[h]` and `DeniedCIDRs[h]` start fresh (static origin handled in resolution phase)

**Proof:** Lines 312-322 of `rdce.py` implement exactly this logic. The `is_role_assumption_transition` predicate correctly identifies AssumeRole boundaries (lines 302-310). When false, the three `copy()` operations preserve the prior hop's stores. No other stores are carried. ∎

### Lemma 2: AssumeRole Reset Invariants

**Statement:** For an AssumeRole transition `e_{h-1} → e_h`:
1. `SessionStrings[h] = ∅` (fresh session)
2. `SessionBoolDomains[h] = ∅` (fresh session)
3. `PrincipalStrings[h] = ∅` (caller tags reset)
4. `PrincipalStrings[h]` is then initialized with `ProducedState[h-1][p_key] = {p_val}` for all `p_key` starting with `"aws:PrincipalTag/"` produced by hop `h-1`
5. `ConfigStrings[h] = ∅` (fresh per hop)
6. `RequestStrings[h] = ∅` (fresh, static origin handled separately)

**Proof:** Lines 323-335 implement exactly this:
- Lines 326-329: `SessionStrings`, `SessionBoolDomains`, `PrincipalStrings` set to empty dicts
- Lines 331-334: Iterate over `produced_state[prev_hop_num]`, extract `aws:PrincipalTag/*` keys, initialize `PrincipalStrings[h][p_key] = {p_val}`
- No carry of `ConfigStrings` or `RequestStrings` (fresh per hop by design)
- Static origin assumption is a scenario-level flag, not a scope carry; handled in IP resolution phase (lines 858-942) ∎

### Lemma 3: AssumeRole Principal Tag Initialization Correctness

**Statement:** The principal tags initialized at hop `h` after AssumeRole are exactly the target role's static attached tags produced by hop `h-1`.

**Proof:** 
- Hop `h-1` (AssumeRole) produces context modifications via `produced_context` list
- The evaluator ingests these into `produced_state[h-1]` (lines 754-758)
- Only tags with key starting with `"aws:PrincipalTag/"` and string values are carried (lines 331-334)
- This matches the CCPF contract: "Target role attached tags produced in AssumeRole hop become initial principal tags on hop_num"
- No other principal tags (session tags, caller tags) are carried — matches "Caller principal tags reset (do not survive boundary)" ∎

### Lemma 4: PIVOT_TRANSITION Request Scope Rebind

**Statement:** For a `PIVOT_TRANSITION` on `aws:SourceIp` from hop `from_hop` to `to_hop`:
- The request IP at `to_hop` is rebound to `ProducedState[from_hop]["network_execution_origin"]`
- The prior request IP constraints (under static origin) do not apply to the rebound IP
- The pivot hop is excluded from static origin accumulation (`pivot_rebound_hops` set, line 799)

**Proof:** Lines 798-835:
- `pivot_rebound_hops.add(trans.to_hop)` excludes `to_hop` from static origin accumulation (line 865)
- `rebound_ip = produced_state[from_hop].get("network_execution_origin")` reads the produced bastion IP
- Check: `rebound_ip ∈ hop_allowed_cidrs[to_hop]` (lines 818-835)
- If not satisfied, UNSAT with explicit contradiction rationale
- This correctly models: attacker's external IP (hop 1) ≠ internal bastion IP (hop 2) ∎

### Lemma 5: IDENTITY_DERIVATION Principal Tag Carrying

**Statement:** For an `IDENTITY_DERIVATION` on variable `tag_var` from `from_hop` to `to_hop`:
- The produced tag `ProducedState[from_hop][tag_var]` is carried forward
- It must satisfy the target hop's `PrincipalStrings[to_hop][tag_var]` requirements
- If not, UNSAT with explicit contradiction

**Proof:** Lines 837-856:
- `produced_tag = prod_from.get(tag_var)` reads the produced tag
- `req_tags_target = hop_principal_strings.get(to_hop, {}).get(tag_var)` reads target requirements
- Check: `produced_tag in req_tags_target` (line 843)
- If violated: UNSAT with "Identity derivation contradiction" rationale
- This correctly implements: target role's static tag (produced at AssumeRole) must satisfy downstream resource's tag requirements ∎

### Lemma 6: Config Scope Fresh Per Hop

**Statement:** `ConfigStrings[h] = ∅` for all `h > 1`. No config-scope values carry across hops.

**Proof:** 
- Initialization at line 289: `hop_config_strings[hop_num] = {}` for every hop
- No carry logic in standard action branch (lines 312-322) — only `PrincipalStrings`, `SessionStrings`, `SessionBoolDomains` are copied
- No carry logic in AssumeRole branch (lines 323-334) — `ConfigStrings` not mentioned
- Produced config values are stored in `produced_state` but never copied to `hop_config_strings` of next hop
- Matches CCPF contract: "CONFIG scope is hop-local; `sts:ExternalId` never carried" ∎

### Lemma 7: No Variable Name Clashes Across Scopes

**Statement:** Keys in different scope stores are never conflated. A key `k` in `PrincipalStrings` is independent of `k` in `SessionStrings`, `ConfigStrings`, `RequestStrings`.

**Proof:**
- Each scope has its own dictionary: `hop_principal_strings`, `hop_session_strings`, `hop_config_strings`, `hop_request_strings`
- All constraint evaluation (lines 558-579) selects the target store by `pred.scope`:
  - `PRINCIPAL` → `hop_principal_strings`
  - `SESSION` → `hop_session_strings`
  - `CONFIG` → `hop_config_strings`
  - `REQUEST` → `hop_request_strings`
- Null assertions use a separate `hop_null_assertions` dict keyed by `(hop, key)` and check all scopes (lines 717-724)
- No code path merges or confuses stores across scopes ∎

---

## 4. Transition Taxonomy Verification

| Transition | Code Location | Formal Rule | Verified |
|------------|---------------|-------------|----------|
| Standard Action | Lines 312-322 | Carry 𝒫, 𝒮; fresh ℛ, 𝒞 | ✓ Lemma 1 |
| AssumeRole | Lines 323-334 | Reset 𝒮, 𝒫; init 𝒫 from produced tags | ✓ Lemmas 2,3 |
| PIVOT_TRANSITION | Lines 798-835 | Rebind ℛ to `network_execution_origin` | ✓ Lemma 4 |
| IDENTITY_DERIVATION | Lines 837-856 | Carry produced 𝒫 tag to target | ✓ Lemma 5 |
| Config Scope | Lines 289, 314-315 | Fresh per hop | ✓ Lemma 6 |
| Scope Separation | Lines 558-579, 717-724 | No cross-scope conflation | ✓ Lemma 7 |

---

## 5. Regression Evidence

### CE3 (Network Pivot) — Verifies Lemma 4
- Fixture: `ce3_transition_permitted.context.json`
- Hop 1: Attacker IP `198.51.100.0/24` (external), produces `network_execution_origin = "10.0.1.100"`
- Hop 2: Requires `10.0.0.0/8` (internal), transition `PIVOT_TRANSITION` on `aws:SourceIp`
- Result: SAT — external IP and internal IP are independent; pivot correctly rebinds
- All 5 A3 tests + 4 Stage B tests pass

### CE6 (Principal Scope Boundary) — Verifies Lemmas 2, 3, 5
- Fixture: `ce6_principal_scope_boundary.context.json` (corrected)
- Hop 1 (AssumeRole): Produces `aws:PrincipalTag/Department = "ApplicationDevelopment"`
- Hop 2: Requires `aws:PrincipalTag/Department == "SecurityOperations"`
- Transition: `IDENTITY_DERIVATION` on `aws:PrincipalTag/Department`
- Result: UNSAT — derived tag `"ApplicationDevelopment"` ≠ required `"SecurityOperations"`
- All 6 A6 tests + 3 Stage B tests pass

### Scope Isolation Tests — Verifies Lemmas 1, 6, 7
- `TestStringEqualsScopeIsolation`: 2000 examples, different scopes never conflict
- `TestRemediationF6_StringScopesHandling`: SESSION, CONFIG, PRINCIPAL all behave correctly
- `TestRemediationF5_ScopeResetsOnlyExplicit`: Principal tags persist across standard actions; reset only at AssumeRole

---

## 6. Limitations and Outstanding Gaps

| Gap | Description | Impact |
|-----|-------------|--------|
| **No inductive proof** | Lemmas proven by code inspection, not structural induction on path length | Cannot guarantee invariance for arbitrary path lengths |
| **Static origin assumption** | Treated as scenario flag, not part of state machine | O3 Claim 2 depends on formalizing this |
| **Produced context ordering** | Preconditions evaluated before produced context (line 337 vs 740) — correct but not formally proven | Could affect Null=false satisfaction if produced context sets required key |
| **Network pivot session/principal** | "Reset/preserved per docs" — not explicitly coded | Minor; PIVOT_TRANSITION only tested for REQUEST scope |

---

## 7. Classification

**O2 Classification: EMPIRICALLY SUPPORTED** (not PROVEN)

- **Proven by code inspection:** All 7 lemmas verified against implementation
- **Empirical evidence:** 156 deterministic tests pass, including CE3, CE6, and all scope regression tests
- **Missing for PROVEN:**
  - Structural induction proof over arbitrary path length
  - Machine-checked proof (Coq/Isabelle)
  - Formalization of static origin assumption as part of state machine
  - Complete case analysis for all transition type combinations

**Dependencies:** O2 depends on O1 (solver soundness for transition constraint evaluation). O2 unblocks O3, O6, O7.

---

## 8. Next Steps

To advance O2 toward PROVEN:
1. Formalize state machine in proof assistant (states, transitions, invariants)
2. Prove Lemmas 1-7 by structural induction on path length
3. Prove no counterexample exists for arbitrary transition sequences
4. Formalize static origin assumption as explicit state component
5. Verify produced context ordering invariant (preconditions before postconditions)

---

*Proof document generated: 2026-10-29*
*Based on RDCE implementation in `research/ccpf/rdce.py` lines 296-335, 798-856*
*Empirical evidence from `tests/research/test_rdce.py`, `test_semantic_validation.py`*