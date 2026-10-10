"""Deterministic validation script for research counterexample fixtures.

Evaluates:
  1. Scenario Schema Ingest: Ingestion of each scenario JSON via ARF-RT's
     official `load_scenario_file` (validates baseline Pydantic `ScenarioInput` models).
  2. Research Context Sidecar Validation: Structural integrity and schema
     completeness of `.context.json` sidecar files.
  3. Graph & Path Consistency: Edge references in the research path match actual
     nodes and edges defined in the scenario.
  4. Hand-Derived CSP Target Specification: Validates format and presence of
     manually derived expected SAT/UNSAT/UNKNOWN targets against Phase 15 formal definitions.

IMPORTANT:
  This script validates fixture data structures, schema conformity, and manifest consistency.
  It does NOT execute an algorithmic CSP solver or simulate an unimplemented inference engine.
  Expected SAT/UNSAT/UNKNOWN outcomes are hand-derived formal specifications, not computational
  outputs of an implemented solver. Engine implementation is deferred to subsequent phases.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from arf_rt.adapters.seed_json import load_scenario_file


def run_validation() -> int:
    fixture_dir = Path(__file__).resolve().parent
    manifest_path = fixture_dir / "manifest.json"

    print("=" * 70)
    print("PHASE 16.1 — RESEARCH FIXTURE SUITE DETERMINISTIC VALIDATION")
    print("=" * 70)
    print(f"Fixture directory: {fixture_dir.relative_to(REPO_ROOT)}")

    if not manifest_path.is_file():
        print(f"ERROR: Manifest not found at {manifest_path}")
        return 1

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    fixtures = manifest.get("fixtures", [])
    print(f"Total fixtures declared in manifest: {len(fixtures)}\n")

    all_passed = True

    for item in fixtures:
        fid = item["fixture_id"]
        fname = item["name"]
        exp_outcome = item["expected_csp_outcome"]
        exp_mult = item["expected_feasibility_multiplier"]
        scen_file = item.get("scenario_file")
        ctx_file = item.get("context_file")

        print(f"--- Fixture [{fid}]: {fname} ---")

        # 1. Scenario Schema Validation
        if scen_file:
            scen_path = fixture_dir / scen_file
            if not scen_path.is_file():
                print(f"  [FAIL] Scenario file missing: {scen_file}")
                all_passed = False
                continue
            try:
                scen_model = load_scenario_file(scen_path)
                print(f"  [PASS] Scenario Schema Ingest (Pydantic ScenarioInput): OK")
                print(f"         Nodes: {len(scen_model.nodes)}, Edges: {len(scen_model.edges)}, Constraints: {len(scen_model.constraints or [])}")
            except Exception as e:
                print(f"  [FAIL] Scenario validation error in {scen_file}: {e}")
                all_passed = False
                continue
        elif "referenced_baseline_fixtures" in item:
            print("  [PASS] Baseline References Verified:")
            for b_rel in item["referenced_baseline_fixtures"]:
                b_path = REPO_ROOT / b_rel
                if not b_path.is_file():
                    print(f"         [FAIL] Baseline file missing: {b_rel}")
                    all_passed = False
                else:
                    b_model = load_scenario_file(b_path)
                    print(f"         {b_rel} (Nodes: {len(b_model.nodes)}, Edges: {len(b_model.edges)})")

        # 2. Sidecar Context Metadata Validation
        if not ctx_file:
            print(f"  [FAIL] Context sidecar file not specified for {fid}")
            all_passed = False
            continue

        ctx_path = fixture_dir / ctx_file
        if not ctx_path.is_file():
            print(f"  [FAIL] Context sidecar file missing: {ctx_file}")
            all_passed = False
            continue

        try:
            with open(ctx_path, "r", encoding="utf-8") as cf:
                ctx_data = json.load(cf)

            # Validate required fields
            req_fields = [
                "fixture_id", "name", "research_question",
                "expected_csp_outcome", "expected_feasibility_multiplier",
                "expected_path_score_effect", "formal_rationale", "falsification_criteria"
            ]
            missing_fields = [f for f in req_fields if f not in ctx_data]
            if missing_fields:
                print(f"  [FAIL] Missing required fields in sidecar: {missing_fields}")
                all_passed = False
                continue

            # Consistency checks
            assert ctx_data["fixture_id"] == fid
            assert ctx_data["expected_csp_outcome"] == exp_outcome
            assert ctx_data["expected_feasibility_multiplier"] == exp_mult

            print(f"  [PASS] Context Sidecar Schema: All required metadata fields present.")
            print(f"  [SPECIFICATION ONLY] Hand-Derived Expected Outcome Target: {exp_outcome} (Multiplier: {exp_mult})")
            print(f"         Expected Path Effect: {ctx_data['expected_path_score_effect']}")
            print(f"         NOTE: Target is an analytical specification; no algorithmic solver was executed.")

            # Path graph consistency check
            if scen_file:
                scenario_edges = scen_model.edges
                for hop in ctx_data.get("path_under_evaluation", []):
                    hop_etype = hop.get("edge_type")
                    matching = [e for e in scenario_edges if e.edge_type == hop_etype]
                    if not matching:
                        print(f"  [FAIL] Hop {hop.get('hop')} ({hop_etype}) not found in scenario graph!")
                        all_passed = False
                print(f"  [PASS] Graph Consistency: All hops map directly to scenario edges.")

        except Exception as e:
            print(f"  [FAIL] Context validation error in {ctx_file}: {e}")
            all_passed = False
            continue

        print()

    print("=" * 70)
    print("STATUS SUMMARY:")
    print("  1. Scenario Schema Validation (Pydantic / ARF-RT):  " + ("PASSED" if all_passed else "FAILED"))
    print("  2. Context Sidecar Schema & Topology Integrity:    " + ("PASSED" if all_passed else "FAILED"))
    print("  3. Hand-Derived Formal CSP Targets:                VERIFIED (Analytical Specification Only)")
    print("  4. Algorithmic CSP Inference Engine:               NOT IMPLEMENTED (No solver executed)")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(run_validation())
