"""Stage 1 stress test fixture generator.

Produces a deterministic synthetic scenario with:
  - ~80 nodes, ~140 edges
  - 3 objectives (prod_admin, infra_admin, billing_admin)
  - 6 correlation components (3 SCP, 1 trust condition, 2 uncorrelated chains)
  - 3 dead-end subgraphs
  - 1 deep chain (length 7)
  - Mixed evidence seeding (2 DENY, 1 ALLOW, rest at prior)

Usage:
    python -m arf_rt.fixtures.generate_stage1 > tests/fixtures/stage1_large.json
"""
from __future__ import annotations

import json
import random
import sys


def generate_stage1(seed: int = 1337) -> dict:
    rng = random.Random(seed)

    nodes: list[dict] = []
    edges: list[dict] = []
    constraints: list[dict] = []
    edge_constraints: list[dict] = []
    observations: list[dict] = []

    # ── Helpers ───────────────────────────────────────────────
    def node(name: str, ntype: str = "IAMRole") -> dict:
        acct = "900000000001"
        prefix = "user" if ntype == "IAMUser" else "role"
        n = {
            "provider": "aws",
            "node_type": ntype,
            "provider_id": f"arn:aws:iam::{acct}:{prefix}/{name}",
            "region": "-",
        }
        nodes.append(n)
        return n

    def edge(src: dict, dst: dict, etype: str = "sts:AssumeRole") -> dict:
        e = {
            "edge_type": etype,
            "src": {k: v for k, v in src.items()},
            "dst": {k: v for k, v in dst.items()},
            "region": "-",
            "features": {},
        }
        edges.append(e)
        return e

    def constraint(ctype: str, scope_id: str, policy_name: str,
                   denied_actions: list[str] | None = None,
                   properties: dict | None = None) -> dict:
        c = {
            "provider": "aws",
            "constraint_type": ctype,
            "scope_type": "OU",
            "scope_id": scope_id,
            "region": "-",
            "properties": properties or {
                "policy_id": f"p-{policy_name.lower().replace(' ', '-')}",
                "policy_name": policy_name,
                "ou_name": scope_id,
                "denied_actions": denied_actions or ["sts:AssumeRole"],
            },
            "status": "ACTIVE",
            "validation_status": "UNVALIDATED",
            "confidence_q": 800,
        }
        constraints.append(c)
        return c

    def bind_edge_constraint(e: dict, c: dict) -> None:
        ec = {
            "edge_ref": {
                "edge_type": e["edge_type"],
                "src": e["src"],
                "dst": e["dst"],
                "region": e["region"],
            },
            "constraint_ref": {
                "provider": c["provider"],
                "constraint_type": c["constraint_type"],
                "scope_type": c["scope_type"],
                "scope_id": c["scope_id"],
                "region": c["region"],
                "properties": c["properties"],
            },
        }
        edge_constraints.append(ec)

    def observe(e: dict, result: str, signal_q: int = 90,
                constraint_relevant: bool = False, tag: str = "") -> None:
        observations.append({
            "edge_ref": {
                "edge_type": e["edge_type"],
                "src": e["src"],
                "dst": e["dst"],
                "region": e["region"],
            },
            "probe_type": "REPLAY_SCRIPTED",
            "result": result,
            "reason_class": "UNKNOWN",
            "strength": "DIRECT",
            "signal_q": signal_q,
            "is_counterfactual": False,
            "constraint_relevant": constraint_relevant,
            "evidence_hash": tag or f"obs_{len(observations)}",
        })

    # ── Layer 0: Attackers (3) ────────────────────────────────
    attackers = [node(f"attacker_{c}", "IAMUser") for c in "abc"]

    # ── Layer 1: Entry roles (12) ─────────────────────────────
    entry = [node(f"entry_{i:02d}") for i in range(12)]

    # Each attacker fans to 4 entry roles
    for i, atk in enumerate(attackers):
        targets = entry[i * 4:(i + 1) * 4]
        for t in targets:
            edge(atk, t)

    # ── Layer 2: Mid-tier roles (24) ──────────────────────────
    mid = [node(f"mid_{i:02d}") for i in range(24)]

    # Each entry fans to 2–3 mid-tier
    for i, ent in enumerate(entry):
        fanout = 2 + (i % 2)  # alternates 2,3,2,3...
        targets_idx = [(i * 2 + j) % len(mid) for j in range(fanout)]
        for idx in targets_idx:
            edge(ent, mid[idx])

    # ── Cross-links in mid-tier (10) ──────────────────────────
    for i in range(10):
        src_idx = (i * 3) % len(mid)
        dst_idx = (i * 3 + 7) % len(mid)
        if src_idx != dst_idx:
            edge(mid[src_idx], mid[dst_idx])

    # ── Layer 3: Governance boundary nodes (10) ───────────────
    gov = [node(f"gov_{i:02d}") for i in range(10)]

    # Mid → governance edges (25)
    for i in range(25):
        src_idx = (i * 3) % len(mid)
        dst_idx = i % len(gov)
        edge(mid[src_idx], gov[dst_idx])

    # ── Layer 4: Targets (3) ──────────────────────────────────
    prod_admin = node("prod_admin")
    infra_admin = node("infra_admin")
    billing_admin = node("billing_admin")
    target_nodes = [prod_admin, infra_admin, billing_admin]

    # ── Correlation Component G1: SCP BlockProd (6 edges) ─────
    c_g1 = constraint("SCP", "ou-prod", "BlockCrossAccountProd")
    g1_edges = []
    for i in range(6):
        e = edge(gov[i % len(gov)], prod_admin)
        bind_edge_constraint(e, c_g1)
        g1_edges.append(e)

    # ── Correlation Component G2: Trust Condition (4 edges) ───
    c_g2 = constraint(
        "TRUST_CONDITION", "ou-external", "ExternalIdRequired",
        properties={
            "policy_id": "p-external-id",
            "policy_name": "ExternalIdRequired",
            "ou_name": "ou-external",
            "condition_type": "sts:ExternalId",
            "denied_actions": ["sts:AssumeRole"],
        },
    )
    g2_edges = []
    for i in range(4):
        e = edge(gov[3 + i], infra_admin)
        bind_edge_constraint(e, c_g2)
        g2_edges.append(e)

    # ── Correlation Component G3: SCP BlockInfra (5 edges) ────
    c_g3 = constraint("SCP", "ou-infra", "BlockInfraAdmin")
    g3_edges = []
    for i in range(5):
        e = edge(gov[5 + (i % 5)], infra_admin)
        bind_edge_constraint(e, c_g3)
        g3_edges.append(e)

    # ── Correlation Component G4: SCP BlockBilling (4 edges) ──
    c_g4 = constraint("SCP", "ou-billing", "BlockBillingAccess")
    g4_edges = []
    for i in range(4):
        e = edge(gov[i + 2], billing_admin)
        bind_edge_constraint(e, c_g4)
        g4_edges.append(e)

    # ── Uncorrelated governance→target edges (6) ──────────────
    for i in range(3):
        edge(gov[7 + (i % 3)], billing_admin)  # uncorrelated paths to billing
    for i in range(3):
        edge(gov[i], infra_admin)  # uncorrelated paths to infra

    # ── Deep chain (length 7) ─────────────────────────────────
    deep = [node(f"deep_{i:02d}") for i in range(6)]
    edge(mid[0], deep[0])
    for i in range(5):
        edge(deep[i], deep[i + 1])
    edge(deep[5], prod_admin)  # alternative deep path to prod_admin

    # ── Dead-end subgraphs (3 × 6 nodes) ─────────────────────
    for sg in range(3):
        dead_nodes = [node(f"dead_{sg}_{i:02d}") for i in range(6)]
        # Connect from mid-tier
        edge(mid[sg * 4], dead_nodes[0])
        edge(mid[sg * 4 + 1], dead_nodes[1])
        # Internal dead-end edges
        for i in range(5):
            edge(dead_nodes[i], dead_nodes[i + 1])
        # Dead ends loop back on themselves (no path to target)
        edge(dead_nodes[5], dead_nodes[0])

    # ── Seed observations ─────────────────────────────────────
    # 2 DENY in G1 (SCP evidence)
    observe(g1_edges[0], "DENY", signal_q=90, constraint_relevant=True, tag="g1_deny_0")
    observe(g1_edges[1], "DENY", signal_q=90, constraint_relevant=True, tag="g1_deny_1")

    # 1 ALLOW in G2
    observe(g2_edges[0], "ALLOW", signal_q=85, tag="g2_allow_0")

    # 1 ALLOW on entry edge (establishes partial chain)
    observe(edges[0], "ALLOW", signal_q=95, tag="entry_allow_0")

    # ── Objectives ────────────────────────────────────────────
    objectives = []
    for atk, tgt, label in [
        (attackers[0], prod_admin, "prod"),
        (attackers[1], infra_admin, "infra"),
        (attackers[2], billing_admin, "billing"),
    ]:
        objectives.append({
            "objective_type": "REACHABILITY",
            "start_nodes": [{
                "provider": atk["provider"],
                "node_type": atk["node_type"],
                "provider_id": atk["provider_id"],
                "region": atk["region"],
            }],
            "target_nodes": [{
                "provider": tgt["provider"],
                "node_type": tgt["node_type"],
                "provider_id": tgt["provider_id"],
                "region": tgt["region"],
            }],
            "max_depth": 8,
            "k": 10,
        })

    # ── Scripted truth map (for eval) ─────────────────────────
    # G1 edges: all DENY (SCP active)
    # G2 edges: all ALLOW (external id present)
    # G3 edges: mixed (3 DENY, 2 ALLOW)
    # G4 edges: all DENY
    # Uncorrelated: all ALLOW
    # Deep chain: all ALLOW
    # Dead ends: all ALLOW (but irrelevant — no path to target)
    # Entry/mid: all ALLOW

    scenario = {
        "nodes": nodes,
        "edges": edges,
        "constraints": constraints,
        "edge_constraints": edge_constraints,
        "objectives": objectives,
        "observations": observations,
    }

    return scenario


def main() -> None:
    scenario = generate_stage1()
    # Stats
    print(json.dumps(scenario, indent=2), file=sys.stdout)
    print(
        f"# Stage 1 fixture: {len(scenario['nodes'])} nodes, "
        f"{len(scenario['edges'])} edges, "
        f"{len(scenario['constraints'])} constraints, "
        f"{len(scenario['edge_constraints'])} edge_constraints, "
        f"{len(scenario['objectives'])} objectives, "
        f"{len(scenario['observations'])} observations",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
