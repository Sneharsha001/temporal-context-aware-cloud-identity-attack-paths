"""Synthetic privilege graph generator for ARF-RT scaling experiments.

Generates layered cloud identity graphs with configurable size and correlation structure.

Usage:
    python generate_fixture.py --edges 100 --correlation none --output scenario_100_nocorr.json
    python generate_fixture.py --edges 1000 --correlation medium --output scenario_1000_corr.json
"""

import json
import hashlib
import random
import argparse
from datetime import datetime, timezone


def deterministic_id(provider, node_type, provider_id, region="-"):
    """Same SHA-256 ID algorithm as IAMScope/BloodHound adapter."""
    canonical = json.dumps(
        {"provider": provider, "node_type": node_type,
         "provider_id": provider_id, "region": region},
        sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def generate_scenario(
    target_edges: int,
    correlation_mode: str,  # "none", "medium", "heavy"
    seed: int = 42,
) -> dict:
    """Generate a layered privilege graph.
    
    Architecture:
        Layer 0: Attacker principals (users/service accounts)
        Layer 1: Jump roles (dev/staging)
        Layer 2: Intermediate roles (cross-account)
        Layer 3: Target admin roles
    
    Correlation modes:
        none   — all edges are uncorrelated singletons
        medium — one 10-edge SCP component + rest singletons
        heavy  — two SCP components (10 + 5 edges) + rest singletons
    """
    rng = random.Random(seed)
    
    # Compute layer sizes from target edge count
    # Each attacker connects to ~3 jump roles, each jump to ~2 intermediates,
    # each intermediate to ~2 targets. So edges ≈ attackers*3 + jumps*2 + intermediates*2
    # Rough: edges ≈ 3*attackers + 2*(3*attackers) + 2*(6*attackers) = 21*attackers
    # So attackers ≈ edges/20
    n_attackers = max(2, target_edges // 20)
    n_jumps = max(3, n_attackers * 3)
    n_intermediates = max(4, n_jumps * 2)
    n_targets = max(2, min(10, n_intermediates // 3))
    
    nodes = []
    edges = []
    
    # Generate nodes
    attackers = []
    for i in range(n_attackers):
        node = {
            "provider": "aws", "node_type": "IAMUser",
            "provider_id": f"arn:aws:iam::100000000000:user/attacker-{i:04d}",
            "region": "-",
            "display_name": f"attacker-{i:04d}",
            "properties": {"account_id": "100000000000", "layer": 0}
        }
        nodes.append(node)
        attackers.append(node)
    
    jumps = []
    for i in range(n_jumps):
        acct = f"{200000000000 + i % 5}"
        node = {
            "provider": "aws", "node_type": "IAMRole",
            "provider_id": f"arn:aws:iam::{acct}:role/JumpRole-{i:04d}",
            "region": "-",
            "display_name": f"JumpRole-{i:04d}",
            "properties": {"account_id": acct, "layer": 1}
        }
        nodes.append(node)
        jumps.append(node)
    
    intermediates = []
    for i in range(n_intermediates):
        acct = f"{300000000000 + i % 8}"
        node = {
            "provider": "aws", "node_type": "IAMRole",
            "provider_id": f"arn:aws:iam::{acct}:role/IntRole-{i:04d}",
            "region": "-",
            "display_name": f"IntRole-{i:04d}",
            "properties": {"account_id": acct, "layer": 2}
        }
        nodes.append(node)
        intermediates.append(node)
    
    targets = []
    for i in range(n_targets):
        node = {
            "provider": "aws", "node_type": "IAMRole",
            "provider_id": f"arn:aws:iam::400000000000:role/ProdAdmin-{i:04d}",
            "region": "-",
            "display_name": f"ProdAdmin-{i:04d}",
            "properties": {"account_id": "400000000000", "layer": 3}
        }
        nodes.append(node)
        targets.append(node)
    
    def make_edge(src_node, dst_node, edge_type="sts:AssumeRole_permission"):
        alpha = rng.choice([1, 2, 2, 3])
        beta = rng.choice([1, 1, 2])
        return {
            "edge_type": edge_type,
            "src": {"provider": src_node["provider"], "node_type": src_node["node_type"],
                    "provider_id": src_node["provider_id"], "region": "-"},
            "dst": {"provider": dst_node["provider"], "node_type": dst_node["node_type"],
                    "provider_id": dst_node["provider_id"], "region": "-"},
            "region": "-",
            "features": {"cross_account": src_node["properties"]["account_id"] != dst_node["properties"]["account_id"]},
            "alpha_i": alpha, "beta_i": beta
        }
    
    # Layer 0 → Layer 1: each attacker connects to 2-4 jump roles
    edge_set = set()
    for atk in attackers:
        n_conn = rng.randint(2, min(4, len(jumps)))
        chosen = rng.sample(jumps, n_conn)
        for j in chosen:
            key = (atk["provider_id"], j["provider_id"])
            if key not in edge_set:
                edges.append(make_edge(atk, j))
                edge_set.add(key)
    
    # Layer 1 → Layer 2: each jump connects to 1-3 intermediates
    for j in jumps:
        n_conn = rng.randint(1, min(3, len(intermediates)))
        chosen = rng.sample(intermediates, n_conn)
        for inter in chosen:
            key = (j["provider_id"], inter["provider_id"])
            if key not in edge_set:
                edges.append(make_edge(j, inter))
                edge_set.add(key)
    
    # Layer 2 → Layer 3: each intermediate connects to 1-2 targets
    for inter in intermediates:
        n_conn = rng.randint(1, min(2, len(targets)))
        chosen = rng.sample(targets, n_conn)
        for tgt in chosen:
            key = (inter["provider_id"], tgt["provider_id"])
            if key not in edge_set:
                edges.append(make_edge(inter, tgt))
                edge_set.add(key)
    
    # Pad or trim to target edge count
    # Add cross-layer shortcuts if we need more edges
    all_non_target = attackers + jumps + intermediates
    while len(edges) < target_edges:
        src = rng.choice(all_non_target)
        src_layer = src["properties"]["layer"]
        # Connect to a node in a higher layer
        if src_layer == 0:
            pool = jumps + intermediates
        elif src_layer == 1:
            pool = intermediates + targets
        else:
            pool = targets
        dst = rng.choice(pool)
        key = (src["provider_id"], dst["provider_id"])
        if key not in edge_set and src["provider_id"] != dst["provider_id"]:
            edges.append(make_edge(src, dst))
            edge_set.add(key)
    
    # Trim if over
    if len(edges) > target_edges:
        edges = edges[:target_edges]
    
    # Generate constraints and edge_constraints based on correlation mode
    constraints = []
    edge_constraints = []
    
    if correlation_mode in ("medium", "heavy"):
        # SCP Component 1: pick 10 cross-account edges and bind to one SCP
        cross_acct_edges = [e for e in edges if e["features"].get("cross_account")]
        if len(cross_acct_edges) >= 10:
            scp1_edges = rng.sample(cross_acct_edges, 10)
        else:
            scp1_edges = cross_acct_edges[:10]
        
        scp1 = {
            "provider": "aws", "constraint_type": "SCP",
            "scope_type": "ou", "scope_id": "ou-prod-001", "region": "-",
            "properties": {
                "policy_id": "scp-BlockCrossAccountAssume",
                "statement_id": "DenyAssumeRoleProd",
                "effect": "DENY", "action": "sts:AssumeRole"
            },
            "status": "ACTIVE", "validation_status": "UNVALIDATED",
            "confidence_q": 500
        }
        constraints.append(scp1)
        
        for e in scp1_edges:
            # Set these edges to DENY-lean prior (SCP governance)
            e["alpha_i"] = 1
            e["beta_i"] = 2
            edge_constraints.append({
                "edge_ref": {
                    "edge_type": e["edge_type"],
                    "src": e["src"], "dst": e["dst"], "region": "-"
                },
                "constraint_ref": {
                    "provider": "aws", "constraint_type": "SCP",
                    "scope_type": "ou", "scope_id": "ou-prod-001", "region": "-",
                    "properties": scp1["properties"]
                }
            })
    
    if correlation_mode == "heavy":
        # SCP Component 2: pick 5 different edges, second SCP
        remaining = [e for e in edges 
                     if e not in scp1_edges and e["features"].get("cross_account")]
        if len(remaining) >= 5:
            scp2_edges = rng.sample(remaining, 5)
        else:
            scp2_edges = remaining[:5]
        
        scp2 = {
            "provider": "aws", "constraint_type": "SCP",
            "scope_type": "ou", "scope_id": "ou-staging-001", "region": "-",
            "properties": {
                "policy_id": "scp-BlockStagingEscalation",
                "statement_id": "DenyIAMWriteStaging",
                "effect": "DENY", "action": "iam:*"
            },
            "status": "ACTIVE", "validation_status": "UNVALIDATED",
            "confidence_q": 500
        }
        constraints.append(scp2)
        
        for e in scp2_edges:
            e["alpha_i"] = 1
            e["beta_i"] = 2
            edge_constraints.append({
                "edge_ref": {
                    "edge_type": e["edge_type"],
                    "src": e["src"], "dst": e["dst"], "region": "-"
                },
                "constraint_ref": {
                    "provider": "aws", "constraint_type": "SCP",
                    "scope_type": "ou", "scope_id": "ou-staging-001", "region": "-",
                    "properties": scp2["properties"]
                }
            })
    
    # Generate ground truth observations (30% of edges observed)
    n_obs = max(1, len(edges) // 3)
    obs_edges = rng.sample(edges, min(n_obs, len(edges)))
    observations = []
    for e in obs_edges:
        # Constrained edges more likely DENY
        is_constrained = any(
            ec["edge_ref"]["src"]["provider_id"] == e["src"]["provider_id"] and
            ec["edge_ref"]["dst"]["provider_id"] == e["dst"]["provider_id"]
            for ec in edge_constraints
        )
        if is_constrained:
            result = rng.choices(["DENY", "ALLOW"], weights=[0.7, 0.3])[0]
        else:
            result = rng.choices(["ALLOW", "DENY"], weights=[0.7, 0.3])[0]
        
        observations.append({
            "edge_ref": {
                "edge_type": e["edge_type"],
                "src": e["src"], "dst": e["dst"], "region": "-"
            },
            "result": result,
            "strength": "DIRECT",
            "signal_q": 95,
            "reason_class": "CONSTRAINT_DENY" if result == "DENY" and is_constrained else "UNKNOWN",
            "observed_at": "2026-03-07T00:00:00Z"
        })
    
    # Objectives: attacker-0000 → all ProdAdmin targets
    objectives = [{
        "objective_type": "reachability",
        "start_nodes": [{
            "provider": "aws", "node_type": "IAMUser",
            "provider_id": attackers[0]["provider_id"], "region": "-"
        }],
        "target_nodes": [{
            "provider": t["provider"], "node_type": t["node_type"],
            "provider_id": t["provider_id"], "region": "-"
        } for t in targets[:3]],  # Top 3 targets
        "max_depth": 6,
        "k": 10
    }]
    
    constrained_count = len(edge_constraints)
    corr_component_sizes = []
    if correlation_mode == "medium":
        corr_component_sizes = [min(10, len(scp1_edges))]
    elif correlation_mode == "heavy":
        corr_component_sizes = [min(10, len(scp1_edges)), min(5, len(scp2_edges))]
    
    scenario = {
        "metadata": {
            "generator": "synthetic_scaling",
            "seed": seed,
            "target_edges": target_edges,
            "correlation_mode": correlation_mode,
            "actual_nodes": len(nodes),
            "actual_edges": len(edges),
            "constrained_edges": constrained_count,
            "constrained_fraction": round(constrained_count / len(edges), 3) if edges else 0,
            "correlation_component_sizes": corr_component_sizes,
            "observations": len(observations),
            "generated_at": datetime.now(timezone.utc).isoformat()
        },
        "nodes": nodes,
        "edges": edges,
        "constraints": constraints,
        "edge_constraints": edge_constraints,
        "objectives": objectives,
        "observations": observations
    }
    
    return scenario


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic ARF-RT scaling fixture")
    parser.add_argument("--edges", type=int, required=True, help="Target edge count")
    parser.add_argument("--correlation", choices=["none", "medium", "heavy"], default="none")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    
    scenario = generate_scenario(args.edges, args.correlation, args.seed)
    
    with open(args.output, "w") as f:
        json.dump(scenario, f, indent=2)
    
    meta = scenario["metadata"]
    print(f"Generated: {meta['actual_nodes']} nodes, {meta['actual_edges']} edges, "
          f"{meta['constrained_edges']} constrained ({meta['constrained_fraction']*100:.0f}%), "
          f"{meta['observations']} observations")
    print(f"Correlation: {meta['correlation_mode']} (components: {meta['correlation_component_sizes']})")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
