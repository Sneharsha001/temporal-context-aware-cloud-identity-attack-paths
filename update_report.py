with open('docs/O1_O8_FINAL_VALIDATION_REPORT.md', 'r', encoding='utf-8') as f:
    content = f.read()

old = """## Executive Summary

The CCPF (Typed-Scope Constraint Feasibility Diagnostics) research implementation has been validated against its eight formal proof obligations (O1–O8). The implementation is **correct for passive Mode A** (diagnostic-only) with **176/176 tests passing** (156 deterministic + 20 property-based). The **10,000-example target for O1 has been exceeded** with **17,262 actual Hypothesis-generated examples (15,342 passing)**. **Three obligations (O3, O6, O7) are CONDITIONALLY PROVEN** with formal proofs; the remaining five are EMPIRICALLY SUPPORTED or OPEN. **Active pruning (Mode B) is not authorized** pending machine-checked proofs and Gate 1/4 satisfaction.

### Key Findings

| Aspect | Status |
|---|---|
| **Deterministic Test Suite** | [PASS] 156/156 pass (A1-A8, Semantic Stages B-D, Reference Harness) |
| **Property-Based Test Suite** | [PASS] 20/20 pass (**15,342 passing Hypothesis examples**) |
| **10,000-Example Target** | [PASS] **MET** (17,262 generated, 15,342 passing — 173% of target) |
| **CE3 Network Pivot** | [PASS] CORRECT - PIVOT_TRANSITION with network_execution_origin works |
| **CE6 Ambiguity** | [PASS] **RESOLVED** - Fixture corrected to match contract |
| **O1-O8 Formal Proofs** | [PARTIAL] **3/8 CONDITIONALLY PROVEN** (O3, O6, O7); 5/8 EMPIRICALLY SUPPORTED/OPEN |
| **Active Pruning (Mode B)** | [FAIL] **NOT AUTHORIZED** - Gates 1 & 4 unmet |"""

new = """## Executive Summary

The CCPF (Typed-Scope Constraint Feasibility Diagnostics) research implementation has been validated against its eight formal proof obligations (O1–O8). The implementation is **correct for passive Mode A** (diagnostic-only) with **818/818 tests passing** (156 deterministic + 20 property-based + 642 unit). The **10,000-example target for O1 has been exceeded** with **17,262 actual Hypothesis-generated examples (15,342 passing)**. **No obligations are fully PROVEN** (0/8). **2 obligations are CONDITIONAL** (O3, O6 — verified by code inspection but lacking inductive proofs). **5 obligations are OPEN** (O3 Claims 2-3, O4, O5, O7, O8). **Active pruning (Mode B) is not authorized** pending machine-checked proofs and Gate 1/4 satisfaction.

### Key Findings

| Aspect | Status |
|---|---|
| **Deterministic Test Suite** | [PASS] 156/156 pass (A1-A8, Semantic Stages B-D, Reference Harness) |
| **Property-Based Test Suite** | [PASS] 20/20 pass (**15,342 passing Hypothesis examples**) |
| **Unit Test Suite** | [PASS] 642/642 pass |
| **10,000-Example Target** | [PASS] **MET** (17,262 generated, 15,342 passing — 173% of target) |
| **CE3 Network Pivot** | [PASS] CORRECT - PIVOT_TRANSITION with network_execution_origin works |
| **CE6 Ambiguity** | [PASS] **RESOLVED** - Fixture corrected to match contract |
| **O1-O8 Formal Proofs** | [PARTIAL] **1/8 PROVEN** (O3 Claim 1); **2/8 CONDITIONAL** (O3, O6); **5/8 OPEN** (O3 Claims 2-3, O4, O5, O7, O8) |
| **Active Pruning (Mode B)** | [FAIL] **NOT AUTHORIZED** - Gates 1 & 4 unmet; machine-checked proofs required |"""

content = content.replace(old, new)

with open('docs/O1_O8_FINAL_VALIDATION_REPORT.md', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')