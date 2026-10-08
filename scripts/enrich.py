"""GhostGates enrichment bridge — connects CI/CD gate analysis to AWS IAM trust.

When a gate is compromised, the OIDC trust edge's prior shifts from
DENY-lean (condition looks protective) to ALLOW-lean (condition is paper-thin).
"""

from __future__ import annotations
import json, sys
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass
class OIDCSubjectClaim:
    org: str; repo: str; branch: str | None; environment: str | None
    tag: str | None; trigger: str | None; raw: str

def parse_oidc_subject(pattern: str) -> OIDCSubjectClaim | None:
    if not pattern.startswith("repo:"): return None
    rest = pattern[5:]
    parts = rest.split(":", 1)
    org_repo = parts[0]; qualifier = parts[1] if len(parts) > 1 else ""
    org, repo = (org_repo.split("/", 1) if "/" in org_repo else (org_repo, "*"))
    branch = environment = tag = trigger = None
    if qualifier.startswith("ref:refs/heads/"): branch = qualifier[15:]
    elif qualifier.startswith("ref:refs/tags/"): tag = qualifier[14:]
    elif qualifier.startswith("environment:"): environment = qualifier[12:]
    elif qualifier == "pull_request": trigger = "pull_request"
    return OIDCSubjectClaim(org=org, repo=repo, branch=branch, environment=environment, tag=tag, trigger=trigger, raw=pattern)

SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}

def match_findings(claim, findings):
    matched = []
    for f in findings:
        repo_full = f.get("repo", "")
        if claim.repo == "*":
            if not repo_full.startswith(f"{claim.org}/"): continue
        else:
            if repo_full != f"{claim.org}/{claim.repo}": continue
        rid = f.get("rule_id", "")
        if rid.startswith("GHOST-OIDC") or rid.startswith("GHOST-WF"):
            matched.append(f); continue
        if claim.branch and f.get("gate_type") == "branch_protection":
            fb = f.get("branch", "")
            if claim.branch == "*" or fb == claim.branch or not fb:
                matched.append(f); continue
        if claim.environment and f.get("gate_type") == "environment":
            if f.get("environment") == claim.environment:
                matched.append(f); continue
    return matched

def _find_oidc_edges_for_pattern(edges, pattern):
    """Find edges whose OIDC subject pattern matches."""
    matched = []
    for e in edges:
        feat = e.get("features", {})
        if feat.get("oidc_subject_pattern") == pattern:
            matched.append(e)
    return matched

def enrich_scenario(scenario, ghostgates_report):
    if not ghostgates_report: return scenario
    findings = ghostgates_report.get("findings", [])
    if not findings: return scenario
    now_iso = datetime.now(timezone.utc).isoformat()
    constraints = scenario.get("constraints", [])
    edges = scenario.get("edges", [])
    edge_constraints = scenario.get("edge_constraints", [])
    
    constraint_by_scope = {}
    for c in constraints:
        if c.get("constraint_type") == "TRUST_CONDITION":
            constraint_by_scope[c["scope_id"]] = c
    
    compromised = validated = edges_adjusted = 0
    for scope_id, constraint in constraint_by_scope.items():
        props = constraint.get("properties", {})
        pattern = props.get("oidc_subject_pattern", "")
        if not pattern: continue
        claim = parse_oidc_subject(pattern)
        if not claim: continue
        matched = match_findings(claim, findings)
        
        if matched:
            max_sev = max((f.get("severity","LOW") for f in matched), key=lambda s: SEVERITY_RANK.get(s,0))
            enrichment_data = {
                "governance_confidence": "compromised",
                "ghostgates_enrichment": {
                    "status": "bypasses_found", "repo": f"{claim.org}/{claim.repo}",
                    "branch": claim.branch, "environment": claim.environment,
                    "findings_count": len(matched), "max_severity": max_sev,
                    "findings_summary": [{"rule_id": f.get("rule_id"), "name": f.get("name"),
                        "severity": f.get("severity"), "attacker_level": f.get("attacker_level")} for f in matched],
                    "enriched_at": now_iso,
                }
            }
            props.update(enrichment_data)
            constraint["properties"] = props
            compromised += 1
            
            # KEY: Adjust edge priors — condition is paper-thin
            # Shift OIDC edges from DENY-lean to ALLOW-lean
            oidc_edges = _find_oidc_edges_for_pattern(edges, pattern)
            for e in oidc_edges:
                old_a, old_b = e.get("alpha_i", 1), e.get("beta_i", 2)
                # Compromised: treat as naked trust
                # CRITICAL bypass (external attacker) → strong ALLOW lean
                # HIGH bypass (repo-admin/write) → moderate ALLOW lean  
                if max_sev == "CRITICAL":
                    e["alpha_i"] = 3
                    e["beta_i"] = 1
                elif max_sev == "HIGH":
                    e["alpha_i"] = 2
                    e["beta_i"] = 1
                else:
                    e["alpha_i"] = 1
                    e["beta_i"] = 1
                
                feat = e.get("features", {})
                feat["prior_adjusted_by_ghostgates"] = True
                feat["prior_before"] = {"alpha": old_a, "beta": old_b}
                feat["prior_reason"] = f"OIDC gate compromised: {max_sev} bypass via {matched[0].get('rule_id')}"
                e["features"] = feat
                edges_adjusted += 1
                
        else:
            scanned_repos = {f.get("repo","") for f in findings}
            if f"{claim.org}/{claim.repo}" in scanned_repos:
                enrichment_data = {
                    "governance_confidence": "externally_validated",
                    "ghostgates_enrichment": {"status": "no_bypasses", "repo": f"{claim.org}/{claim.repo}",
                        "branch": claim.branch, "environment": claim.environment,
                        "findings_count": 0, "enriched_at": now_iso}
                }
                props.update(enrichment_data)
                constraint["properties"] = props
                validated += 1
                
                # Validated: strengthen DENY prior — gate is solid
                oidc_edges = _find_oidc_edges_for_pattern(edges, pattern)
                for e in oidc_edges:
                    old_a, old_b = e.get("alpha_i", 1), e.get("beta_i", 2)
                    e["alpha_i"] = 1
                    e["beta_i"] = 4  # Strong DENY — gate confirmed enforced
                    feat = e.get("features", {})
                    feat["prior_adjusted_by_ghostgates"] = True
                    feat["prior_before"] = {"alpha": old_a, "beta": old_b}
                    feat["prior_reason"] = "OIDC gate externally validated — no bypasses found"
                    e["features"] = feat
                    edges_adjusted += 1
        
        # Update edge_constraint refs to match
        for ec in edge_constraints:
            cref = ec.get("constraint_ref", {})
            if isinstance(cref, dict) and cref.get("scope_id") == scope_id:
                cref["properties"] = constraint["properties"]
    
    meta = scenario.get("metadata", {})
    meta["ghostgates_enrichment"] = {
        "oidc_constraints_found": len(constraint_by_scope),
        "compromised": compromised, "externally_validated": validated,
        "edges_prior_adjusted": edges_adjusted,
        "ghostgates_findings_total": len(findings),
        "ghostgates_org": ghostgates_report.get("org"),
    }
    scenario["metadata"] = meta
    return scenario

def main():
    import argparse
    p = argparse.ArgumentParser(description="Enrich IAMScope scenario with GhostGates findings")
    p.add_argument("--scenario", required=True); p.add_argument("--ghostgates", required=True); p.add_argument("--output", required=True)
    args = p.parse_args()
    with open(args.scenario) as f: scenario = json.load(f)
    with open(args.ghostgates) as f: report = json.load(f)
    enriched = enrich_scenario(scenario, report)
    with open(args.output, "w") as f: json.dump(enriched, f, indent=2)
    meta = enriched.get("metadata",{}).get("ghostgates_enrichment",{})
    print(f"Enrichment complete:")
    print(f"  COMPROMISED (gate bypassable): {meta.get('compromised',0)}")
    print(f"  VALIDATED (gate solid): {meta.get('externally_validated',0)}")
    print(f"  Edge priors adjusted: {meta.get('edges_prior_adjusted',0)}")
    print(f"  GhostGates findings used: {meta.get('ghostgates_findings_total',0)}")

if __name__ == "__main__": main()
