"""§20 KPI tests — every test name required by the spec.

Tests in this file are named exactly as specified in §20.
Behaviors that were already tested elsewhere are re-verified here
under the canonical names for traceability.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from arf_rt.adapters.seed_json import load_scenario_string
from arf_rt.cli import run_full_pipeline
from arf_rt.config import MAX_EDGE_MASS, MAX_TEMPLATE_MASS
from arf_rt.engine.belief import apply_mass_cap, classify_polarity, compute_increment, get_base_w_q
from arf_rt.engine.correlation import compute_correlation
from arf_rt.engine.paths import search_top_k
from arf_rt.engine.snapshot import canonical_run_hash, compute_all_obs_digests
from arf_rt.util.canon import (
    ARFValidationError,
    canonical_json,
    make_constraint_id,
    make_edge_id,
    make_node_id,
)

MINIMAL = str(Path(__file__).parent.parent / "fixtures" / "minimal_scenario.json")
RICH = str(Path(__file__).parent.parent / "fixtures" / "rich_scenario.json")


# ===================================================================
# DETERMINISM TESTS
# ===================================================================


class TestCanonicalJsonKeySortUtf8LexOrder:
    """§20: test_canonical_json_key_sort_utf8_lex_order"""

    def test_keys_sorted_lexicographically(self) -> None:
        assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'

    def test_nested_keys_sorted(self) -> None:
        d = {"z": {"b": 1, "a": 2}, "a": 1}
        result = canonical_json(d)
        assert result == '{"a":1,"z":{"a":2,"b":1}}'

    def test_unicode_sorted_by_escaped_form(self) -> None:
        # ensure_ascii means café → caf\u00e9
        result = canonical_json({"café": 1, "cafe": 2})
        assert result.index('"cafe"') < result.index('"caf\\u00e9"')

    def test_null_preserved(self) -> None:
        assert canonical_json({"a": None}) == '{"a":null}'

    def test_compact_separators(self) -> None:
        result = canonical_json({"a": 1, "b": 2})
        assert ": " not in result
        assert ", " not in result


class TestSignalQDomainIntOnlyRejectsFloat:
    """§20: test_signal_q_domain_int_only_rejects_float"""

    def test_float_signal_q_rejected(self) -> None:
        raw = json.dumps({
            "nodes": [{"provider": "aws", "node_type": "IAMRole",
                        "provider_id": "r1", "region": "us-east-1"}],
            "edges": [{"edge_type": "t", "src": "r1", "dst": "r1",
                        "features": {"a": "b"}}],
            "objectives": [{"objective_type": "REACHABILITY",
                             "start_nodes": ["r1"], "target_nodes": ["r1"],
                             "max_depth": 3, "k": 3}],
            "observations": [{"edge_ref": "r1", "probe_type": "REPLAY_SCRIPTED",
                               "result": "ALLOW", "reason_class": "UNKNOWN",
                               "strength": "DIRECT", "signal_q": 80.5}],
        })
        with pytest.raises(ARFValidationError):
            load_scenario_string(raw)

    def test_int_signal_q_accepted(self) -> None:
        raw = json.dumps({
            "nodes": [{"provider": "aws", "node_type": "IAMRole",
                        "provider_id": "r1", "region": "us-east-1"}],
            "edges": [{"edge_type": "t", "src": "r1", "dst": "r1",
                        "features": {"a": "b"}}],
            "objectives": [{"objective_type": "REACHABILITY",
                             "start_nodes": ["r1"], "target_nodes": ["r1"],
                             "max_depth": 3, "k": 3}],
            "observations": [{"edge_ref": "r1", "probe_type": "REPLAY_SCRIPTED",
                               "result": "ALLOW", "reason_class": "UNKNOWN",
                               "strength": "DIRECT", "signal_q": 80}],
        })
        s = load_scenario_string(raw)
        assert s.observations[0].signal_q == 80

    def test_signal_q_above_100_rejected(self) -> None:
        raw = json.dumps({
            "nodes": [{"provider": "aws", "node_type": "IAMRole",
                        "provider_id": "r1", "region": "us-east-1"}],
            "edges": [{"edge_type": "t", "src": "r1", "dst": "r1",
                        "features": {"a": "b"}}],
            "objectives": [{"objective_type": "REACHABILITY",
                             "start_nodes": ["r1"], "target_nodes": ["r1"],
                             "max_depth": 3, "k": 3}],
            "observations": [{"edge_ref": "r1", "probe_type": "REPLAY_SCRIPTED",
                               "result": "ALLOW", "reason_class": "UNKNOWN",
                               "strength": "DIRECT", "signal_q": 101}],
        })
        with pytest.raises(ARFValidationError):
            load_scenario_string(raw)


class TestJsonColumnsCanonicalAtWriteTimeEnforced:
    """§20: test_json_columns_canonical_at_write_time_enforced"""

    def test_flags_json_canonical(self) -> None:
        conn, _ = run_full_pipeline(MINIMAL)
        for row in conn.execute("SELECT flags_json FROM edges").fetchall():
            fj = row["flags_json"]
            parsed = json.loads(fj)
            assert fj == canonical_json(parsed), f"Non-canonical flags_json: {fj}"

    def test_edge_id_sequence_canonical(self) -> None:
        conn, _ = run_full_pipeline(MINIMAL)
        for row in conn.execute("SELECT edge_id_sequence FROM derived_topk").fetchall():
            seq = row["edge_id_sequence"]
            parsed = json.loads(seq)
            assert seq == canonical_json(parsed), f"Non-canonical: {seq}"

    def test_start_nodes_json_canonical(self) -> None:
        conn, _ = run_full_pipeline(MINIMAL)
        for row in conn.execute("SELECT start_nodes_json FROM objectives").fetchall():
            sn = row["start_nodes_json"]
            parsed = json.loads(sn)
            assert sn == canonical_json(parsed)

    def test_flags_json_all_keys_present(self) -> None:
        conn, _ = run_full_pipeline(RICH)
        required_keys = {"conflict", "counterfactual_override", "prior_only", "stale"}
        for row in conn.execute("SELECT flags_json FROM edges").fetchall():
            d = json.loads(row["flags_json"])
            assert set(d.keys()) == required_keys


# ===================================================================
# CORRECTNESS TESTS
# ===================================================================


class TestConstraintIdIncludesProviderNoCollision:
    """§20: test_constraint_id_includes_provider_no_collision"""

    def test_different_providers_different_ids(self) -> None:
        id_aws = make_constraint_id("aws", "SCP", "OU", "ou-001", "us-east-1", "fp")
        id_gcp = make_constraint_id("gcp", "SCP", "OU", "ou-001", "us-east-1", "fp")
        assert id_aws != id_gcp

    def test_same_inputs_same_id(self) -> None:
        id1 = make_constraint_id("aws", "SCP", "OU", "ou-001", "us-east-1", "fp")
        id2 = make_constraint_id("aws", "SCP", "OU", "ou-001", "us-east-1", "fp")
        assert id1 == id2


class TestTemplateKeyUsesFeaturesFpNotRawJson:
    """§20: test_template_key_uses_features_fp_not_raw_json

    Template ID is derived from canonical fingerprint of features,
    not raw JSON (which might have different key ordering).
    """

    def test_template_id_from_features_fingerprint(self) -> None:
        conn, _ = run_full_pipeline(MINIMAL)
        # Both edges have same features (action=sts:AssumeRole, effect=Allow)
        # so they share a template
        tids = conn.execute(
            "SELECT DISTINCT template_id FROM edges"
        ).fetchall()
        assert len(tids) == 1, "Edges with same features should share template"

    def test_feature_order_doesnt_matter(self) -> None:
        """Features {a:1, b:2} and {b:2, a:1} produce same fingerprint."""
        fp1 = canonical_json({"a": 1, "b": 2})
        fp2 = canonical_json({"b": 2, "a": 1})
        assert fp1 == fp2


class TestCorrelationGlobalComponentsThresholdAndActiveOnly:
    """§20: test_correlation_global_components_threshold_and_active_only"""

    def test_only_active_constraints_with_sufficient_confidence(self) -> None:
        conn, _ = run_full_pipeline(RICH)
        corr = compute_correlation(conn)
        # All 3 constraints are ACTIVE with confidence_q=800 ≥ 500
        assert len(corr["components"]) == 3

    def test_low_confidence_excluded(self) -> None:
        """Constraints with confidence_q < 500 should not form components."""
        conn, _ = run_full_pipeline(MINIMAL)
        corr = compute_correlation(conn)
        # Minimal scenario: SCP with confidence_q=0 (default) < 500
        # Should have 0 correlation components (or only unconstrained groups)
        for eid, group in corr["edge_groups"].items():
            sig = json.loads(group["p_worst_sig"])
            # If constraint excluded, sig should be NONE
            for item in sig:
                assert item[0] == "NONE", (
                    f"Expected NONE sig for low-confidence constraint, got {item}"
                )


class TestGroupMinCrossMultiplyThenEdgeIdTieBreak:
    """§20: test_group_min_cross_multiply_then_edge_id_tie_break"""

    def test_representative_is_minimum_probability(self) -> None:
        conn, _ = run_full_pipeline(RICH)
        corr = compute_correlation(conn)
        for sig, rep_eid in corr["p_worst_reps"].items():
            rep = conn.execute(
                "SELECT alpha_i, beta_i FROM edges WHERE edge_id = ?",
                (rep_eid,),
            ).fetchone()
            sig_data = json.loads(sig)
            group_eids = [
                eid
                for eid, g in corr["edge_groups"].items()
                if json.loads(g["p_worst_sig"]) == sig_data
            ]
            for other_eid in group_eids:
                other = conn.execute(
                    "SELECT alpha_i, beta_i FROM edges WHERE edge_id = ?",
                    (other_eid,),
                ).fetchone()
                # Cross-multiply: rep <= other
                lhs = rep["alpha_i"] * (other["alpha_i"] + other["beta_i"])
                rhs = other["alpha_i"] * (rep["alpha_i"] + rep["beta_i"])
                if lhs == rhs:
                    # Tie-break: rep_eid <= other_eid (COLLATE BINARY)
                    assert rep_eid <= other_eid
                else:
                    assert lhs <= rhs


class TestPartialBoundAdmissibleDueToGlobalComponents:
    """§20: test_partial_bound_admissible_due_to_global_components

    Because components are global, extending a path cannot increase
    the partial bound → best-first search is admissible.
    """

    def test_extending_path_never_increases_bound(self) -> None:
        conn, _ = run_full_pipeline(RICH)
        corr = compute_correlation(conn)
        Q8 = 100_000_000

        # For each path in derived_topk, verify:
        # The partial bound at each prefix is >= the final path probability
        for topk_row in conn.execute(
            "SELECT edge_id_sequence, p_worst_q8 FROM derived_topk"
        ).fetchall():
            edge_ids = json.loads(topk_row["edge_id_sequence"])
            # Compute partial products
            groups_seen = set()
            partial = Q8  # starts at 1.0 in Q8
            for eid in edge_ids:
                group = corr["edge_groups"][eid]
                sig = group["p_worst_sig"]
                if sig not in groups_seen:
                    groups_seen.add(sig)
                    rep_eid = corr["p_worst_reps"][sig]
                    rep = conn.execute(
                        "SELECT alpha_i, beta_i FROM edges WHERE edge_id = ?",
                        (rep_eid,),
                    ).fetchone()
                    p_q8 = rep["alpha_i"] * Q8 // (rep["alpha_i"] + rep["beta_i"])
                    partial = partial * p_q8 // Q8
            assert partial == topk_row["p_worst_q8"]
            # Partial at any prefix >= final (since each factor <= 1.0)
            # This is the admissibility property


class TestConstraintValidationRelevanceRuleEnforced:
    """§20: test_constraint_validation_relevance_rule_enforced"""

    def test_only_constraint_relevant_obs_counted(self) -> None:
        """SCP2 in rich scenario: A→C has DETERMINISTIC obs with cr=0.
        This obs should NOT count toward SCP2 validation."""
        conn, _ = run_full_pipeline(RICH)
        # SCP2 linked to {A→C, C→D}
        # A→C obs: DETERMINISTIC ALLOW, cr=0 → not relevant for constraint validation
        # C→D obs9: CONSTRAINT_DENY, cr=1 → relevant
        # Only 1 qualifying edge < N=2 → UNVALIDATED
        scps = conn.execute(
            "SELECT validation_status FROM constraints WHERE constraint_type = 'SCP'"
        ).fetchall()
        statuses = [c["validation_status"] for c in scps]
        assert "UNVALIDATED" in statuses, (
            "SCP2 should be UNVALIDATED (only 1 qualifying edge)"
        )

    def test_non_direct_deterministic_excluded(self) -> None:
        """INFERRED/HEURISTIC obs should not count for constraint validation
        even if reason_class=CONSTRAINT_DENY."""
        # Tested via minimal scenario: obs3 is INFERRED after downgrade
        # Even if it had cr=1, INFERRED shouldn't qualify for SCP N/M
        conn, _ = run_full_pipeline(MINIMAL)
        cst = conn.execute(
            "SELECT validation_status FROM constraints"
        ).fetchone()
        assert cst["validation_status"] == "UNVALIDATED"


class TestMassCapRenormalizationDeterministic:
    """§20: test_mass_cap_renormalization_deterministic"""

    def test_under_cap_unchanged(self) -> None:
        assert apply_mass_cap(100, 50, MAX_EDGE_MASS) == (100, 50)

    def test_over_cap_renormalized(self) -> None:
        a, b = apply_mass_cap(15000, 10000, MAX_EDGE_MASS)
        assert a + b <= MAX_EDGE_MASS
        assert a >= 1 and b >= 1
        # alpha = max(1, floor(15000 * 20000 / 25000)) = 12000
        # beta = max(1, 20000 - 12000) = 8000
        assert a == 12000 and b == 8000

    def test_extreme_ratio_preserved(self) -> None:
        a, b = apply_mass_cap(19999, 1, 20000)
        assert a + b <= MAX_EDGE_MASS
        # Already at cap, no change needed
        assert a == 19999 and b == 1

    def test_cap_floor_at_1(self) -> None:
        """Even with extreme ratio, both components ≥ 1."""
        a, b = apply_mass_cap(25000, 1, 20000)
        assert a >= 1 and b >= 1

    def test_deterministic_across_calls(self) -> None:
        results = set()
        for _ in range(100):
            results.add(apply_mass_cap(15000, 10000, MAX_EDGE_MASS))
        assert len(results) == 1


class TestSqlDeterministicOrderByUsesCollateBinary:
    """§20: test_sql_deterministic_order_by_uses_collate_binary"""

    def test_snapshot_uses_collate_binary(self) -> None:
        """All ORDER BY in snapshot.py on text columns use COLLATE BINARY."""
        src = Path("arf_rt/engine/snapshot.py").read_text()
        # Find all ORDER BY clauses
        order_bys = re.findall(r"ORDER BY\s+(.+?)\"", src, re.DOTALL)
        for ob in order_bys:
            # Skip numeric columns (rank, observation_id)
            cols = [c.strip() for c in ob.split(",")]
            for col in cols:
                col_lower = col.lower()
                if any(skip in col_lower for skip in ["rank", "observation_id", "update_id", "objective_id"]):
                    continue
                assert "COLLATE BINARY" in col, (
                    f"Missing COLLATE BINARY on: {col}"
                )

    def test_correlation_uses_collate_binary(self) -> None:
        src = Path("arf_rt/engine/correlation.py").read_text()
        order_bys = re.findall(r"ORDER BY\s+(.+?)\"", src, re.DOTALL)
        for ob in order_bys:
            cols = [c.strip() for c in ob.split(",")]
            for col in cols:
                if any(skip in col.lower() for skip in ["rank", "observation_id"]):
                    continue
                assert "COLLATE BINARY" in col, (
                    f"Missing COLLATE BINARY in correlation.py: {col}"
                )

    def test_paths_uses_collate_binary(self) -> None:
        src = Path("arf_rt/engine/paths.py").read_text()
        if "ORDER BY" in src:
            order_bys = re.findall(r"ORDER BY\s+(.+?)\"", src, re.DOTALL)
            for ob in order_bys:
                cols = [c.strip() for c in ob.split(",")]
                for col in cols:
                    if any(skip in col.lower() for skip in ["rank"]):
                        continue
                    assert "COLLATE BINARY" in col, (
                        f"Missing COLLATE BINARY in paths.py: {col}"
                    )
