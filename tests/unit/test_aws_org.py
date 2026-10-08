"""Tests for Session 12B: AWS Org constraint resolution + trust policy parsing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arf_rt.adapters.aws_org import (
    OrgStructure,
    account_ancestors,
    action_matches_pattern,
    load_org_structure,
    resolve_scp_constraints,
    scp_denied_actions,
    scp_denies_action,
    scps_for_account,
)
from arf_rt.adapters.pmapper import translate_from_file
from arf_rt.adapters.trust_policy_parser import (
    parse_trust_conditions,
    resolve_trust_constraints,
)
from arf_rt.adapters.scenario_builder import build_scenario

PMAPPER_FIXTURE = str(Path(__file__).parent.parent / "fixtures" / "pmapper_graph.json")
ORG_FIXTURE = str(Path(__file__).parent.parent / "fixtures" / "aws_org.json")


# ===================================================================
# OU hierarchy traversal
# ===================================================================


class TestOUHierarchy:
    def test_load_org(self) -> None:
        org = load_org_structure(ORG_FIXTURE)
        assert org.org_id == "o-testorg123"
        assert org.root_id == "r-root1"
        assert len(org.ous) == 3
        assert len(org.accounts) == 3

    def test_dev_account_ancestors(self) -> None:
        """111 is in ou-dev, which is under r-root1."""
        org = load_org_structure(ORG_FIXTURE)
        chain = account_ancestors(org, "111111111111")
        assert chain == ["ou-dev", "r-root1"]

    def test_prod_account_ancestors(self) -> None:
        org = load_org_structure(ORG_FIXTURE)
        chain = account_ancestors(org, "222222222222")
        assert chain == ["ou-prod", "r-root1"]

    def test_shared_account_ancestors(self) -> None:
        org = load_org_structure(ORG_FIXTURE)
        chain = account_ancestors(org, "333333333333")
        assert chain == ["ou-shared", "r-root1"]

    def test_unknown_account_empty(self) -> None:
        org = load_org_structure(ORG_FIXTURE)
        assert account_ancestors(org, "999999999999") == []

    def test_scps_for_dev_account(self) -> None:
        """Dev account gets: DenyCreateAccessKey (ou-dev), DenyAssumeRoleUnlessVPN (ou-dev),
        DenyDangerousActionsOrgWide (root)."""
        org = load_org_structure(ORG_FIXTURE)
        scps = scps_for_account(org, "111111111111")
        names = [scp.name for _, scp in scps]
        assert "DenyCreateAccessKey" in names
        assert "DenyAssumeRoleUnlessVPN" in names
        assert "DenyDangerousActionsOrgWide" in names
        assert len(scps) == 3

    def test_scps_for_prod_account(self) -> None:
        """Prod gets: DenyAssumeRoleFromProd (ou-prod), DenyDangerousActionsOrgWide (root)."""
        org = load_org_structure(ORG_FIXTURE)
        scps = scps_for_account(org, "222222222222")
        names = [scp.name for _, scp in scps]
        assert "DenyAssumeRoleFromProd" in names
        assert "DenyDangerousActionsOrgWide" in names
        assert len(scps) == 2


# ===================================================================
# SCP action matching
# ===================================================================


class TestActionMatching:
    def test_exact_match(self) -> None:
        assert action_matches_pattern("sts:AssumeRole", "sts:AssumeRole")

    def test_exact_mismatch(self) -> None:
        assert not action_matches_pattern("s3:GetObject", "sts:AssumeRole")

    def test_wildcard_all(self) -> None:
        assert action_matches_pattern("sts:AssumeRole", "*")
        assert action_matches_pattern("s3:GetObject", "*")

    def test_service_wildcard(self) -> None:
        assert action_matches_pattern("sts:AssumeRole", "sts:*")
        assert not action_matches_pattern("s3:GetObject", "sts:*")

    def test_prefix_wildcard(self) -> None:
        assert action_matches_pattern("iam:CreateAccessKey", "iam:Create*")
        assert not action_matches_pattern("iam:DeleteAccessKey", "iam:Create*")

    def test_case_insensitive(self) -> None:
        assert action_matches_pattern("STS:AssumeRole", "sts:assumerole")

    def test_action_list_in_scp(self) -> None:
        """SCP with Action list should match each independently."""
        from arf_rt.adapters.aws_org import SCPPolicy
        scp = SCPPolicy(
            policy_id="test",
            name="test",
            document={
                "Version": "2012-10-17",
                "Statement": [
                    {"Effect": "Deny", "Action": ["iam:CreateAccessKey", "iam:CreateLoginProfile"]}
                ],
            },
        )
        assert len(scp_denies_action(scp, "iam:CreateAccessKey")) == 1
        assert len(scp_denies_action(scp, "iam:CreateLoginProfile")) == 1
        assert len(scp_denies_action(scp, "iam:DeleteAccessKey")) == 0


class TestSCPParsing:
    def test_explicit_deny_detected(self) -> None:
        org = load_org_structure(ORG_FIXTURE)
        scp = org.scp_policies["p-deny-assume-prod"]
        denied = scp_denied_actions(scp)
        assert len(denied) == 1
        assert denied[0].action_pattern == "sts:AssumeRole"

    def test_allow_statement_ignored(self) -> None:
        """DenyDangerousActionsOrgWide has an Allow * statement — should be ignored."""
        org = load_org_structure(ORG_FIXTURE)
        scp = org.scp_policies["p-deny-dangerous"]
        denied = scp_denied_actions(scp)
        # Only the Deny actions, not the Allow
        patterns = [d.action_pattern for d in denied]
        assert "iam:CreateUser" in patterns
        assert "iam:AttachRolePolicy" in patterns
        assert "*" not in patterns  # Allow * should not appear

    def test_conditional_deny_flagged(self) -> None:
        """DenyAssumeRoleUnlessVPN has conditions → has_conditions=True."""
        org = load_org_structure(ORG_FIXTURE)
        scp = org.scp_policies["p-deny-conditional"]
        denied = scp_denied_actions(scp)
        assert len(denied) == 1
        assert denied[0].has_conditions is True

    def test_conditional_deny_skipped_by_default(self) -> None:
        """Conservative: conditional deny is NOT matched when skip_conditional=True."""
        org = load_org_structure(ORG_FIXTURE)
        scp = org.scp_policies["p-deny-conditional"]
        matches = scp_denies_action(scp, "sts:AssumeRole", skip_conditional=True)
        assert len(matches) == 0

    def test_conditional_deny_included_when_requested(self) -> None:
        org = load_org_structure(ORG_FIXTURE)
        scp = org.scp_policies["p-deny-conditional"]
        matches = scp_denies_action(scp, "sts:AssumeRole", skip_conditional=False)
        assert len(matches) == 1


# ===================================================================
# SCP → edge constraint resolution
# ===================================================================


class TestSCPConstraintResolution:
    def test_constraint_count(self) -> None:
        """3 distinct SCPs create constraints."""
        translated = translate_from_file(PMAPPER_FIXTURE)
        org = load_org_structure(ORG_FIXTURE)
        constraints, _, _ = resolve_scp_constraints(org, translated.edges)
        assert len(constraints) == 3

    def test_edge_constraint_count(self) -> None:
        """3 edges match SCP denies."""
        translated = translate_from_file(PMAPPER_FIXTURE)
        org = load_org_structure(ORG_FIXTURE)
        _, ec, _ = resolve_scp_constraints(org, translated.edges)
        assert len(ec) == 3

    def test_prod_assume_role_blocked(self) -> None:
        """ProdAppRole→ProdDBAccess (sts:AssumeRole, acct 222) blocked by DenyAssumeRoleFromProd."""
        translated = translate_from_file(PMAPPER_FIXTURE)
        org = load_org_structure(ORG_FIXTURE)
        _, ec, _ = resolve_scp_constraints(org, translated.edges)
        prod_links = [
            e for e in ec
            if "ProdAppRole" in e["edge_ref"]["src"]["provider_id"]
            and "ProdDBAccess" in e["edge_ref"]["dst"]["provider_id"]
        ]
        assert len(prod_links) == 1
        assert "DenyAssumeRoleFromProd" in prod_links[0]["constraint_ref"]["properties"]["policy_name"]

    def test_shared_attach_policy_blocked(self) -> None:
        """SharedServiceRole→SharedAdmin (iam:AttachRolePolicy, acct 333) blocked by DenyDangerousActionsOrgWide."""
        translated = translate_from_file(PMAPPER_FIXTURE)
        org = load_org_structure(ORG_FIXTURE)
        _, ec, _ = resolve_scp_constraints(org, translated.edges)
        shared_links = [
            e for e in ec
            if "SharedServiceRole" in e["edge_ref"]["src"]["provider_id"]
            and "SharedAdmin" in e["edge_ref"]["dst"]["provider_id"]
        ]
        assert len(shared_links) == 1
        assert "DenyDangerousActionsOrgWide" in shared_links[0]["constraint_ref"]["properties"]["policy_name"]

    def test_dev_create_key_blocked(self) -> None:
        """ci-deploy→LambdaExecRole (iam:CreateAccessKey, acct 111) blocked by DenyCreateAccessKey."""
        translated = translate_from_file(PMAPPER_FIXTURE)
        org = load_org_structure(ORG_FIXTURE)
        _, ec, _ = resolve_scp_constraints(org, translated.edges)
        dev_links = [
            e for e in ec
            if "ci-deploy" in e["edge_ref"]["src"]["provider_id"]
            and "LambdaExecRole" in e["edge_ref"]["dst"]["provider_id"]
            and e["edge_ref"]["edge_type"] == "iam:CreateAccessKey"
        ]
        assert len(dev_links) == 1

    def test_conditional_scp_produces_warning(self) -> None:
        """DenyAssumeRoleUnlessVPN has conditions → warning emitted."""
        translated = translate_from_file(PMAPPER_FIXTURE)
        org = load_org_structure(ORG_FIXTURE)
        _, _, warnings = resolve_scp_constraints(org, translated.edges)
        conditional_warnings = [w for w in warnings if "conditions" in w.lower()]
        assert len(conditional_warnings) >= 1

    def test_unknown_action_skipped(self) -> None:
        """Edges with UNKNOWN or ADMIN_ACCESS action are not matched."""
        translated = translate_from_file(PMAPPER_FIXTURE)
        org = load_org_structure(ORG_FIXTURE)
        _, ec, _ = resolve_scp_constraints(org, translated.edges)
        admin_links = [
            e for e in ec if e["edge_ref"]["edge_type"] in ("UNKNOWN", "ADMIN_ACCESS")
        ]
        assert len(admin_links) == 0

    def test_constraint_has_arf_format(self) -> None:
        translated = translate_from_file(PMAPPER_FIXTURE)
        org = load_org_structure(ORG_FIXTURE)
        constraints, _, _ = resolve_scp_constraints(org, translated.edges)
        for c in constraints:
            assert c["provider"] == "aws"
            assert c["constraint_type"] == "SCP"
            assert c["scope_type"] in ("OU", "ACCOUNT")
            assert c["status"] == "ACTIVE"
            assert c["confidence_q"] == 800
            assert "policy_id" in c["properties"]
            assert "denied_actions" in c["properties"]


# ===================================================================
# Trust policy parsing
# ===================================================================


class TestTrustPolicyParsing:
    def test_external_id_detected(self) -> None:
        trust_doc = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": "arn:aws:iam::111:root"},
                "Action": "sts:AssumeRole",
                "Condition": {"StringEquals": {"sts:ExternalId": "secret-123"}},
            }],
        }
        conds = parse_trust_conditions("arn:aws:iam::222:role/R", trust_doc)
        assert len(conds) == 1
        assert conds[0].condition_type == "EXTERNAL_ID"
        assert conds[0].values == ["secret-123"]

    def test_org_membership_detected(self) -> None:
        trust_doc = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": "sts:AssumeRole",
                "Condition": {"StringEquals": {"aws:PrincipalOrgID": "o-xxx"}},
            }],
        }
        conds = parse_trust_conditions("arn:aws:iam::333:role/R", trust_doc)
        assert len(conds) == 1
        assert conds[0].condition_type == "ORG_MEMBERSHIP"

    def test_source_ip_detected(self) -> None:
        trust_doc = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": "sts:AssumeRole",
                "Condition": {"IpAddress": {"aws:SourceIp": "10.0.0.0/8"}},
            }],
        }
        conds = parse_trust_conditions("arn:aws:iam::123:role/R", trust_doc)
        assert len(conds) == 1
        assert conds[0].condition_type == "SOURCE_IP"

    def test_mfa_required_detected(self) -> None:
        trust_doc = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": "arn:aws:iam::111:root"},
                "Action": "sts:AssumeRole",
                "Condition": {"Bool": {"aws:MultiFactorAuthPresent": "true"}},
            }],
        }
        conds = parse_trust_conditions("arn:aws:iam::222:role/R", trust_doc)
        assert len(conds) == 1
        assert conds[0].condition_type == "MFA_REQUIRED"

    def test_tag_condition_detected(self) -> None:
        trust_doc = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": "sts:AssumeRole",
                "Condition": {"StringEquals": {"aws:PrincipalTag/team": "security"}},
            }],
        }
        conds = parse_trust_conditions("arn:aws:iam::123:role/R", trust_doc)
        assert len(conds) == 1
        assert conds[0].condition_type == "TAG_CONDITION"

    def test_no_conditions_empty(self) -> None:
        trust_doc = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }],
        }
        conds = parse_trust_conditions("arn:aws:iam::123:role/R", trust_doc)
        assert len(conds) == 0

    def test_deny_statement_ignored(self) -> None:
        """Only Allow statements with conditions matter for trust restrictions."""
        trust_doc = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Deny",
                "Principal": {"AWS": "*"},
                "Action": "sts:AssumeRole",
                "Condition": {"StringEquals": {"sts:ExternalId": "blocked"}},
            }],
        }
        conds = parse_trust_conditions("arn:aws:iam::123:role/R", trust_doc)
        assert len(conds) == 0

    def test_multiple_conditions_in_one_statement(self) -> None:
        trust_doc = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {
                        "sts:ExternalId": "secret",
                        "aws:PrincipalOrgID": "o-test",
                    },
                },
            }],
        }
        conds = parse_trust_conditions("arn:aws:iam::123:role/R", trust_doc)
        types = {c.condition_type for c in conds}
        assert types == {"EXTERNAL_ID", "ORG_MEMBERSHIP"}


class TestTrustConstraintResolution:
    def test_trust_constraint_count(self) -> None:
        """ProdAdmin has ExternalId, SharedServiceRole has PrincipalOrgID → 2 constraints."""
        translated = translate_from_file(PMAPPER_FIXTURE)
        constraints, _, _ = resolve_trust_constraints(
            translated.trust_policies, translated.edges
        )
        assert len(constraints) == 2

    def test_trust_edge_constraint_count(self) -> None:
        """DevOps→ProdAdmin, DevOps→Shared, Lambda→Shared → 3 linkages."""
        translated = translate_from_file(PMAPPER_FIXTURE)
        _, ec, _ = resolve_trust_constraints(
            translated.trust_policies, translated.edges
        )
        assert len(ec) == 3

    def test_external_id_links_to_prod_admin(self) -> None:
        translated = translate_from_file(PMAPPER_FIXTURE)
        _, ec, _ = resolve_trust_constraints(
            translated.trust_policies, translated.edges
        )
        ext_id_links = [
            e for e in ec
            if e["constraint_ref"]["properties"]["condition_type"] == "EXTERNAL_ID"
        ]
        assert len(ext_id_links) == 1
        assert "ProdAdmin" in ext_id_links[0]["edge_ref"]["dst"]["provider_id"]

    def test_org_membership_links_to_shared(self) -> None:
        translated = translate_from_file(PMAPPER_FIXTURE)
        _, ec, _ = resolve_trust_constraints(
            translated.trust_policies, translated.edges
        )
        org_links = [
            e for e in ec
            if e["constraint_ref"]["properties"]["condition_type"] == "ORG_MEMBERSHIP"
        ]
        assert len(org_links) == 2
        for link in org_links:
            assert "SharedServiceRole" in link["edge_ref"]["dst"]["provider_id"]


# ===================================================================
# Full scenario builder
# ===================================================================


class TestScenarioBuilder:
    def test_build_pmapper_only(self) -> None:
        """PMapper graph without org data → no constraints."""
        scenario = build_scenario(
            PMAPPER_FIXTURE,
            objectives=[{
                "objective_type": "REACHABILITY",
                "start_nodes": [{"provider": "aws", "node_type": "IAMUser",
                    "provider_id": "arn:aws:iam::111111111111:user/ci-deploy", "region": "-"}],
                "target_nodes": [{"provider": "aws", "node_type": "IAMRole",
                    "provider_id": "arn:aws:iam::222222222222:role/ProdDBAccess", "region": "-"}],
                "max_depth": 6, "k": 5,
            }],
        )
        assert len(scenario["nodes"]) == 9
        assert len(scenario["edges"]) == 12
        assert len(scenario["constraints"]) == 2  # trust conditions only
        assert len(scenario["objectives"]) == 1

    def test_build_with_org(self) -> None:
        """PMapper + org data → SCP + trust constraints."""
        scenario = build_scenario(
            PMAPPER_FIXTURE,
            org_path=ORG_FIXTURE,
            objectives=[{
                "objective_type": "REACHABILITY",
                "start_nodes": [{"provider": "aws", "node_type": "IAMUser",
                    "provider_id": "arn:aws:iam::111111111111:user/ci-deploy", "region": "-"}],
                "target_nodes": [{"provider": "aws", "node_type": "IAMRole",
                    "provider_id": "arn:aws:iam::222222222222:role/ProdDBAccess", "region": "-"}],
                "max_depth": 6, "k": 5,
            }],
        )
        assert len(scenario["constraints"]) == 5  # 3 SCP + 2 trust
        assert len(scenario["edge_constraints"]) == 6  # 3 SCP + 3 trust

    def test_scenario_has_all_keys(self) -> None:
        scenario = build_scenario(PMAPPER_FIXTURE, objectives=[])
        for key in ("nodes", "edges", "constraints", "edge_constraints",
                     "objectives", "observations"):
            assert key in scenario

    def test_no_objectives_allowed(self) -> None:
        """Building without objectives succeeds (empty list)."""
        scenario = build_scenario(PMAPPER_FIXTURE)
        assert scenario["objectives"] == []

    def test_custom_confidence(self) -> None:
        scenario = build_scenario(
            PMAPPER_FIXTURE,
            org_path=ORG_FIXTURE,
            scp_confidence_q=600,
            trust_confidence_q=400,
        )
        scp_c = [c for c in scenario["constraints"] if c["constraint_type"] == "SCP"]
        trust_c = [c for c in scenario["constraints"] if c["constraint_type"] == "TRUST_CONDITION"]
        for c in scp_c:
            assert c["confidence_q"] == 600
        for c in trust_c:
            assert c["confidence_q"] == 400
