python -m arf_rt.cli analyze scenario_enriched.json --format both
python -m arf_rt.cli plan scenario_enriched.json
Enrichment complete:
  COMPROMISED (gate bypassable): 3
  VALIDATED (gate solid): 0
  Edge priors adjusted: 3
  GhostGates findings used: 4
# ARF-RT Analysis Report

## Summary

| Metric | Count |
|--------|-------|
| Nodes | 8 |
| Edges | 9 |
| Constraints | 3 |
| Objectives | 1 |
| Observations | 0 |

## Objective: reachability

**From:** dev-engineer
**To:** ProdAdminRole (TARGET)
**Max depth:** 6, **K:** 10

### Top-K Attack Paths

| Rank | Confidence | Length | Flags |
|------|------------|--------|-------|
| 1 | LOW | 3 | PRIOR_ONLY |
| 2 | LOW | 3 | PRIOR_ONLY |
| 3 | LOW | 3 | PRIOR_ONLY |

**Path 1** (LOW):
  1. dev-engineer →[repo:Write]→ GitHub Actions: infra-terraform (HYPOTHESIZED)
  2. GitHub Actions: infra-terraform →[oidc:AssumeRole]→ InfraProvisionRole (HYPOTHESIZED)
  3. InfraProvisionRole →[sts:AssumeRole_permission]→ ProdAdminRole (TARGET) (HYPOTHESIZED)

**Path 2** (LOW):
  1. dev-engineer →[repo:Write]→ GitHub Actions: payment-api (HYPOTHESIZED)
  2. GitHub Actions: payment-api →[oidc:AssumeRole]→ ProdDeployRole (HYPOTHESIZED)
  3. ProdDeployRole →[sts:AssumeRole_permission]→ ProdAdminRole (TARGET) (HYPOTHESIZED)

**Path 3** (LOW):
  1. dev-engineer →[repo:Write]→ GitHub Actions: db-migrations (HYPOTHESIZED)
  2. GitHub Actions: db-migrations →[oidc:AssumeRole]→ ProdDBMigrationRole (HYPOTHESIZED)
  3. ProdDBMigrationRole →[sts:AssumeRole_permission]→ ProdAdminRole (TARGET) (HYPOTHESIZED)


## Evidence Coverage

**0** of **9** edges observed with DIRECT/DETERMINISTIC non-counterfactual evidence (**0%**).

## Constraint Validation

| Status | Count |
|--------|-------|
| UNVALIDATED | 3 |

{
  "canonical_run_hash": "e6eb248c31a5358d9b64ac9bc68c9539ee0ab0a0ac6b63d0c146d718cc15a44f",
  "conflicts": [],
  "constraint_validation": [
    {
      "confidence_q": 300,
      "constraint_id": "360e282014edfa5fbe9d24d045cd0ba5021d03cd1219a17c891e44589ce81d97",
      "constraint_type": "TRUST_CONDITION",
      "status": "ACTIVE",
      "validation_status": "UNVALIDATED"
    },
    {
      "confidence_q": 500,
      "constraint_id": "9b0d014d995584446609f9fd29ce0d4f2f243cfc974ada82ab05e304d25df7cf",
      "constraint_type": "TRUST_CONDITION",
      "status": "ACTIVE",
      "validation_status": "UNVALIDATED"
    },
    {
      "confidence_q": 500,
      "constraint_id": "c74d3d59899340c5aaa1cc989c964011cfeedae3af3cbd11d5bd68f72a4f79e5",
      "constraint_type": "TRUST_CONDITION",
      "status": "ACTIVE",
      "validation_status": "UNVALIDATED"
    }
  ],
  "evidence_coverage": {
    "coverage_percent": 0,
    "observed_edges": 0,
    "total_edges": 9
  },
  "objectives": [
    {
      "k": 10,
      "max_depth": 6,
      "objective_id": "fe7f1d713d4bbce243809678cec9d407247bc8aad544c54eb6843fb74bb9d37c",
      "objective_type": "reachability",
      "paths": [
        {
          "confidence_band": "LOW",
          "edge_id_sequence": [
            "e2fd34bbf812d3af48969643f189aa6119bf7c50b35de0ade9e2fbf972aece01",
            "4203913eafa18b08648614417086b7026ae02695d758694d9b54ea4aa294a89c",
            "9d1d74976aaa825f6f728abaf1aab26757b3c8b46ce1355799fb2e631f364b69"
          ],
          "flags": {
            "conflict": false,
            "counterfactual_override": false,
            "prior_only": true,
            "stale": false
          },
          "p_best_q8": 37499999,
          "p_worst_q8": 37499999,
          "path_length": 3,
          "rank": 1
        },
        {
          "confidence_band": "LOW",
          "edge_id_sequence": [
            "8c19d59db6fb8db480e2c8d24d8500369991d22adca734d5b8da7fe2ef81fc74",
            "6c88495b37900884cc9bc5365e6b5186afd6e3f25b293fd598e68085878cf3cc",
            "8a3a42ac27389deabc224ebeb266526a7c135d806d922208d2274a5a6cacc608"
          ],
          "flags": {
            "conflict": false,
            "counterfactual_override": false,
            "prior_only": true,
            "stale": false
          },
          "p_best_q8": 33333332,
          "p_worst_q8": 33333332,
          "path_length": 3,
          "rank": 2
        },
        {
          "confidence_band": "LOW",
          "edge_id_sequence": [
            "0710ce3404c2f9339faebea0c196e5d56c7f8386e3ecdb1ef140b6a0f8f1c703",
            "52f528373c5f2be532bbf31d04a496e11e83e074cf60841af9b7c642279e5a0c",
            "027e8776097bd745d5f33089a28e005a022ec0d8242ac77552a94c09e2f44d9f"
          ],
          "flags": {
            "conflict": false,
            "counterfactual_override": false,
            "prior_only": true,
            "stale": false
          },
          "p_best_q8": 24999999,
          "p_worst_q8": 24999999,
          "path_length": 3,
          "rank": 3
        }
      ],
      "start_nodes": [
        "8acb331236cf439af28c9b57815ed373e8b7248effebc72636235bc4942c703d"
      ],
      "target_nodes": [
        "c226b2e37a7c3d5a249c7ca9b84dcb0142b62efb2edeebf351647d3efabce928"
      ]
    }
  ],
  "obs_digests": {},
  "semantics_version": "1.0.0",
  "summary": {
    "constraint_count": 3,
    "edge_count": 9,
    "node_count": 8,
    "objective_count": 1,
    "observation_count": 0
  },
  "warnings": []
}
canonical_run_hash: e6eb248c31a5358d9b64ac9bc68c9539ee0ab0a0ac6b63d0c146d718cc15a44f
{
  "baseline_entropy": 1.2130076335956181,
  "top_recommendation": {
    "edge_id": "52f528373c5f2be532bbf31d04a496e11e83e074cf60841af9b7c642279e5a0c",
    "eig": 0.23065311459959825,
    "reasons": [
      "appears on a Top-K path",
      "in TRUST_CONDITION correlation component",
      "current correlation group representative",
      "high uncertainty (p=0.50, \u03b1\u2248\u03b2)",
      "never directly probed"
    ]
  },
  "candidates": [
    {
      "edge_id": "52f528373c5f2be532bbf31d04a496e11e83e074cf60841af9b7c642279e5a0c",
      "eig": 0.230653,
      "p_edge": 0.5,
      "reasons": [
        "appears on a Top-K path",
        "in TRUST_CONDITION correlation component",
        "current correlation group representative",
        "high uncertainty (p=0.50, \u03b1\u2248\u03b2)",
        "never directly probed"
      ]
    },
    {
      "edge_id": "027e8776097bd745d5f33089a28e005a022ec0d8242ac77552a94c09e2f44d9f",
      "eig": 0.154404,
      "p_edge": 0.6667,
      "reasons": [
        "appears on a Top-K path",
        "current correlation group representative",
        "high uncertainty (p=0.67, \u03b1\u2248\u03b2)",
        "never directly probed"
      ]
    },
    {
      "edge_id": "6c88495b37900884cc9bc5365e6b5186afd6e3f25b293fd598e68085878cf3cc",
      "eig": 0.154404,
      "p_edge": 0.6667,
      "reasons": [
        "appears on a Top-K path",
        "in TRUST_CONDITION correlation component",
        "current correlation group representative",
        "high uncertainty (p=0.67, \u03b1\u2248\u03b2)",
        "never directly probed"
      ]
    },
    {
      "edge_id": "8a3a42ac27389deabc224ebeb266526a7c135d806d922208d2274a5a6cacc608",
      "eig": 0.154404,
      "p_edge": 0.6667,
      "reasons": [
        "appears on a Top-K path",
        "current correlation group representative",
        "high uncertainty (p=0.67, \u03b1\u2248\u03b2)",
        "never directly probed"
      ]
    },
    {
      "edge_id": "9d1d74976aaa825f6f728abaf1aab26757b3c8b46ce1355799fb2e631f364b69",
      "eig": 0.154404,
      "p_edge": 0.6667,
      "reasons": [
        "appears on a Top-K path",
        "current correlation group representative",
        "high uncertainty (p=0.67, \u03b1\u2248\u03b2)",
        "never directly probed"
      ]
    },
    {
      "edge_id": "0710ce3404c2f9339faebea0c196e5d56c7f8386e3ecdb1ef140b6a0f8f1c703",
      "eig": 0.116279,
      "p_edge": 0.75,
      "reasons": [
        "appears on a Top-K path",
        "current correlation group representative",
        "never directly probed"
      ]
    },
    {
      "edge_id": "4203913eafa18b08648614417086b7026ae02695d758694d9b54ea4aa294a89c",
      "eig": 0.116279,
      "p_edge": 0.75,
      "reasons": [
        "appears on a Top-K path",
        "in TRUST_CONDITION correlation component",
        "current correlation group representative",
        "never directly probed"
      ]
    },
    {
      "edge_id": "8c19d59db6fb8db480e2c8d24d8500369991d22adca734d5b8da7fe2ef81fc74",
      "eig": 0.116279,
      "p_edge": 0.75,
      "reasons": [
        "appears on a Top-K path",
        "current correlation group representative",
        "never directly probed"
      ]
    },
    {
      "edge_id": "e2fd34bbf812d3af48969643f189aa6119bf7c50b35de0ade9e2fbf972aece01",
      "eig": 0.116279,
      "p_edge": 0.75,
      "reasons": [
        "appears on a Top-K path",
        "current correlation group representative",
        "never directly probed"
      ]
    }
  ],
  "component_summary": [
    {
      "component_sig": "[[\"TRUST_CONDITION\",\"9b0d014d995584446609f9fd29ce0d4f2f243cfc974ada82ab05e304d25df7cf\"]]",
      "component_label": "Correlated (TRUST_CONDITION)",
      "edge_count": 1,
      "best_probe_edge": "52f528373c5f2be532bbf31d04a496e11e83e074cf60841af9b7c642279e5a0c",
      "best_eig": 0.23065311459959825
    },
    {
      "component_sig": "[[\"NONE\",\"027e8776097bd745d5f33089a28e005a022ec0d8242ac77552a94c09e2f44d9f\"]]",
      "component_label": "Uncorrelated",
      "edge_count": 1,
      "best_probe_edge": "027e8776097bd745d5f33089a28e005a022ec0d8242ac77552a94c09e2f44d9f",
      "best_eig": 0.15440401607086374
    },
    {
      "component_sig": "[[\"TRUST_CONDITION\",\"c74d3d59899340c5aaa1cc989c964011cfeedae3af3cbd11d5bd68f72a4f79e5\"]]",
      "component_label": "Correlated (TRUST_CONDITION)",
      "edge_count": 1,
      "best_probe_edge": "6c88495b37900884cc9bc5365e6b5186afd6e3f25b293fd598e68085878cf3cc",
      "best_eig": 0.15440401607086374
    },
    {
      "component_sig": "[[\"NONE\",\"8a3a42ac27389deabc224ebeb266526a7c135d806d922208d2274a5a6cacc608\"]]",
      "component_label": "Uncorrelated",
      "edge_count": 1,
      "best_probe_edge": "8a3a42ac27389deabc224ebeb266526a7c135d806d922208d2274a5a6cacc608",
      "best_eig": 0.15440401607086374
    },
    {
      "component_sig": "[[\"NONE\",\"9d1d74976aaa825f6f728abaf1aab26757b3c8b46ce1355799fb2e631f364b69\"]]",
      "component_label": "Uncorrelated",
      "edge_count": 1,
      "best_probe_edge": "9d1d74976aaa825f6f728abaf1aab26757b3c8b46ce1355799fb2e631f364b69",
      "best_eig": 0.15440401607086374
    },
    {
      "component_sig": "[[\"NONE\",\"0710ce3404c2f9339faebea0c196e5d56c7f8386e3ecdb1ef140b6a0f8f1c703\"]]",
      "component_label": "Uncorrelated",
      "edge_count": 1,
      "best_probe_edge": "0710ce3404c2f9339faebea0c196e5d56c7f8386e3ecdb1ef140b6a0f8f1c703",
      "best_eig": 0.11627946680649659
    },
    {
      "component_sig": "[[\"TRUST_CONDITION\",\"360e282014edfa5fbe9d24d045cd0ba5021d03cd1219a17c891e44589ce81d97\"]]",
      "component_label": "Correlated (TRUST_CONDITION)",
      "edge_count": 1,
      "best_probe_edge": "4203913eafa18b08648614417086b7026ae02695d758694d9b54ea4aa294a89c",
      "best_eig": 0.11627946680649659
    },
    {
      "component_sig": "[[\"NONE\",\"8c19d59db6fb8db480e2c8d24d8500369991d22adca734d5b8da7fe2ef81fc74\"]]",
      "component_label": "Uncorrelated",
      "edge_count": 1,
      "best_probe_edge": "8c19d59db6fb8db480e2c8d24d8500369991d22adca734d5b8da7fe2ef81fc74",
      "best_eig": 0.11627946680649659
    },
    {
      "component_sig": "[[\"NONE\",\"e2fd34bbf812d3af48969643f189aa6119bf7c50b35de0ade9e2fbf972aece01\"]]",
      "component_label": "Uncorrelated",
      "edge_count": 1,
      "best_probe_edge": "e2fd34bbf812d3af48969643f189aa6119bf7c50b35de0ade9e2fbf972aece01",
      "best_eig": 0.11627946680649659
    }
  ],
  "stats": {
    "total_edges": 9,
    "candidate_edges": 9,
    "forks_executed": 18,
    "runtime_ms": 16.1
  }
}
Recommendation: probe 52f528373c5f2be5... (EIG=0.2307, appears on a Top-K path, in TRUST_CONDITION correlation component, current correlation group representative, high uncertainty (p=0.50, α≈β), never directly probed)
Stats: 9 edges, 9 candidates, 18 forks, 16ms
