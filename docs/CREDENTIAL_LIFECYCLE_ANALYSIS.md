# Credential Lifecycle and Session Timeline Analysis

**Project:** ARF-RT Temporal Extension  
**Subsystem:** `arf_rt.temporal.timeline`  
**Date:** 2026-10-23  

---

## 1. Mathematical Foundation for Multi-Hop Chaining

In cloud identity graphs, an adversary traverses a multi-hop path $P = (e_1, e_2, \dots, e_k)$ by assuming sequential IAM roles:
$$\text{Principal}_0 \xrightarrow{e_1} \text{Role}_1 \xrightarrow{e_2} \text{Role}_2 \dots \xrightarrow{e_k} \text{Target}$$

Each hop $e_i$ produces an ephemeral STS token with:
- Issuance timestamp: $T_{\text{issued}}(e_i)$
- Maximum configured duration: $D_{\text{max}}(e_i) \in [900, 43200]$ seconds
- Expiration timestamp: $T_{\text{expiry}}(e_i) = T_{\text{issued}}(e_i) + D_{\text{max}}(e_i)$

### Causal Chaining Invariant
For a path to be temporally feasible, every hop $e_{i+1}$ must be assumed strictly before the credential of the prior hop $e_i$ expires:
$$\forall i \in \{1, \dots, k-1\}: \quad T_{\text{issued}}(e_{i+1}) < T_{\text{expiry}}(e_i)$$

Furthermore, actions taken at step $e_i$ must occur within its active validity window:
$$\forall i \in \{1, \dots, k\}: \quad T_{\text{observed}}(e_i) \in \left[ T_{\text{issued}}(e_i), T_{\text{expiry}}(e_i) \right]$$

---

## 2. Visual Timeline Reconstruction

The `CredentialTimelineBuilder` module reconstructs the overlapping validity windows of credentials across all hops and renders an ASCII Gantt chart:

```text
Timeline Span: 2026-10-23T10:00:00 -> 2026-10-23T11:25:00 (5100s)
---------------------------------------------------------------------------
edge_hop1            |[==============================]                     |
edge_hop2            |           [==============================]           |
---------------------------------------------------------------------------
```

### Key Analytical Insights
1. **Critical Path Window:** The intersection of active session windows dictates the maximum possible dwell time for an attacker before credential renewal is mandatory.
2. **Causal Dead Zones:** If $T_{\text{issued}}(e_{i+1}) > T_{\text{expiry}}(e_i)$, the chain breaks irrevocably, proving the attack path infeasible regardless of graph connectivity.

---

## 3. Command Line Interface

Generate lifecycle charts for any candidate path:
```bash
python scripts/visualize_path_timeline.py \
  --path "user->roleA,roleA->roleB,roleB->target" \
  --hints hints.json \
  --chart \
  --table \
  --out timeline_report.md
```
