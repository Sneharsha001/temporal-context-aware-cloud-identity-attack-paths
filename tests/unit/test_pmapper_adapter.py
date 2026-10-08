"""Tests for Session 12A: ARN parser, reason parser, PMapper graph loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arf_rt.adapters.arn import (
    ARNComponents,
    arn_to_node_type,
    arn_to_provider_id,
    arn_to_region,
    extract_account_id,
    parse_arn,
)
from arf_rt.adapters.reason_parser import ParsedReason, parse_reason
from arf_rt.adapters.pmapper import (
    load_pmapper_graph,
    translate_from_file,
    translate_pmapper_graph,
)
from arf_rt.util.canon import ARFValidationError

FIXTURE = str(Path(__file__).parent.parent / "fixtures" / "pmapper_graph.json")


# ===================================================================
# ARN Parser
# ===================================================================


class TestParseARN:
    def test_iam_role(self) -> None:
        c = parse_arn("arn:aws:iam::123456789012:role/MyRole")
        assert c.partition == "aws"
        assert c.service == "iam"
        assert c.region == ""
        assert c.account_id == "123456789012"
        assert c.resource_type == "role"
        assert c.resource_id == "MyRole"

    def test_iam_user(self) -> None:
        c = parse_arn("arn:aws:iam::123456789012:user/admin")
        assert c.resource_type == "user"
        assert c.resource_id == "admin"

    def test_iam_role_with_path(self) -> None:
        c = parse_arn("arn:aws:iam::123456789012:role/service-role/MyLambdaRole")
        assert c.resource_type == "role"
        assert c.resource_id == "service-role/MyLambdaRole"

    def test_lambda_function(self) -> None:
        c = parse_arn("arn:aws:lambda:us-east-1:123456789012:function:my-func")
        assert c.service == "lambda"
        assert c.region == "us-east-1"
        assert c.resource_type == "function"
        assert c.resource_id == "my-func"

    def test_s3_bucket(self) -> None:
        c = parse_arn("arn:aws:s3:::my-bucket")
        assert c.service == "s3"
        assert c.region == ""
        assert c.account_id == ""
        assert c.resource_type == ""
        assert c.resource_id == "my-bucket"

    def test_ec2_instance(self) -> None:
        c = parse_arn("arn:aws:ec2:us-west-2:123456789012:instance/i-1234567890abcdef0")
        assert c.service == "ec2"
        assert c.region == "us-west-2"
        assert c.resource_type == "instance"

    def test_assumed_role(self) -> None:
        c = parse_arn("arn:aws:sts::123456789012:assumed-role/MyRole/session-name")
        assert c.service == "sts"
        assert c.resource_type == "assumed-role"
        assert c.resource_id == "MyRole/session-name"

    def test_govcloud_partition(self) -> None:
        c = parse_arn("arn:aws-us-gov:iam::123456789012:role/GovRole")
        assert c.partition == "aws-us-gov"
        assert c.resource_type == "role"

    def test_china_partition(self) -> None:
        c = parse_arn("arn:aws-cn:iam::123456789012:role/ChinaRole")
        assert c.partition == "aws-cn"

    def test_invalid_arn_raises(self) -> None:
        with pytest.raises(ARFValidationError):
            parse_arn("not-an-arn")

    def test_empty_arn_raises(self) -> None:
        with pytest.raises(ARFValidationError):
            parse_arn("")


class TestARNHelpers:
    def test_extract_account_id(self) -> None:
        assert extract_account_id("arn:aws:iam::123456789012:role/R") == "123456789012"

    def test_extract_account_id_empty(self) -> None:
        assert extract_account_id("arn:aws:s3:::bucket") == ""

    def test_arn_to_node_type_role(self) -> None:
        assert arn_to_node_type("arn:aws:iam::123:role/R") == "IAMRole"

    def test_arn_to_node_type_user(self) -> None:
        assert arn_to_node_type("arn:aws:iam::123:user/U") == "IAMUser"

    def test_arn_to_node_type_lambda(self) -> None:
        assert arn_to_node_type("arn:aws:lambda:us-east-1:123:function:F") == "LambdaFunction"

    def test_arn_to_node_type_s3(self) -> None:
        assert arn_to_node_type("arn:aws:s3:::bucket") == "S3Bucket"

    def test_arn_to_node_type_ec2(self) -> None:
        assert arn_to_node_type("arn:aws:ec2:us-east-1:123:instance/i-123") == "EC2Instance"

    def test_arn_to_node_type_assumed_role(self) -> None:
        assert arn_to_node_type("arn:aws:sts::123:assumed-role/R/session") == "IAMRole"

    def test_arn_to_node_type_unknown(self) -> None:
        result = arn_to_node_type("arn:aws:sqs:us-east-1:123:my-queue")
        assert result == "sqs"  # fallback: service name

    def test_arn_to_region_global(self) -> None:
        assert arn_to_region("arn:aws:iam::123:role/R") == "-"

    def test_arn_to_region_regional(self) -> None:
        assert arn_to_region("arn:aws:lambda:us-east-1:123:function:F") == "us-east-1"

    def test_arn_to_provider_id_role(self) -> None:
        assert arn_to_provider_id("arn:aws:iam::123:role/MyRole") == "MyRole"

    def test_arn_to_provider_id_pathed_role(self) -> None:
        assert arn_to_provider_id("arn:aws:iam::123:role/path/to/R") == "path/to/R"

    def test_arn_to_provider_id_assumed_role(self) -> None:
        assert arn_to_provider_id("arn:aws:sts::123:assumed-role/R/session") == "R"


# ===================================================================
# Reason Parser
# ===================================================================


class TestReasonParser:
    def test_direct_call_assume_role(self) -> None:
        r = parse_reason("can call sts:AssumeRole to access")
        assert r.action == "sts:AssumeRole"
        assert r.mechanism == "direct_call"
        assert r.confidence == "HIGH"

    def test_access_via_assume_role(self) -> None:
        """Real PMapper v1.1.5 format: 'can access via sts:AssumeRole'."""
        r = parse_reason("can access via sts:AssumeRole")
        assert r.action == "sts:AssumeRole"
        assert r.mechanism == "direct_call"
        assert r.confidence == "HIGH"

    def test_access_via_other_actions(self) -> None:
        """Real PMapper uses 'can access via' for all direct actions."""
        r = parse_reason("can access via iam:CreateAccessKey")
        assert r.action == "iam:CreateAccessKey"
        assert r.confidence == "HIGH"

    def test_direct_call_create_access_key(self) -> None:
        r = parse_reason("can call iam:CreateAccessKey to access")
        assert r.action == "iam:CreateAccessKey"
        assert r.mechanism == "direct_call"
        assert r.confidence == "HIGH"

    def test_direct_call_attach_policy(self) -> None:
        r = parse_reason("can call iam:AttachRolePolicy to access")
        assert r.action == "iam:AttachRolePolicy"
        assert r.confidence == "HIGH"

    def test_direct_call_put_user_policy(self) -> None:
        r = parse_reason("can call iam:PutUserPolicy to access")
        assert r.action == "iam:PutUserPolicy"

    def test_admin_access(self) -> None:
        r = parse_reason("(admin) can access")
        assert r.action == "ADMIN_ACCESS"
        assert r.mechanism == "admin"
        assert r.confidence == "HIGH"

    def test_ec2_run_instance(self) -> None:
        r = parse_reason("can use EC2 to run an instance with an existing instance profile to access")
        assert r.action == "ec2:RunInstances"
        assert r.mechanism == "ec2"
        assert r.confidence == "MEDIUM"

    def test_ec2_new_instance_profile(self) -> None:
        r = parse_reason("can use EC2 to run an instance with a newly created instance profile to access")
        assert r.action == "ec2:RunInstances"
        assert r.mechanism == "ec2"

    def test_lambda(self) -> None:
        r = parse_reason("can use Lambda to edit an existing function to access")
        assert r.action == "lambda:UpdateFunctionCode"
        assert r.mechanism == "lambda"
        assert r.confidence == "MEDIUM"

    def test_ssm(self) -> None:
        r = parse_reason("can use SSM to access")
        assert r.action == "ssm:StartSession"
        assert r.mechanism == "ssm"

    def test_cloudformation(self) -> None:
        r = parse_reason("can use CloudFormation to access")
        assert r.action == "cloudformation:CreateStack"
        assert r.mechanism == "cloudformation"

    def test_sagemaker(self) -> None:
        r = parse_reason("can use SageMaker to access")
        assert r.action == "sagemaker:CreateNotebookInstance"

    def test_glue(self) -> None:
        r = parse_reason("can use Glue to access")
        assert r.action == "glue:CreateDevEndpoint"

    def test_codebuild(self) -> None:
        r = parse_reason("can use CodeBuild to access")
        assert r.action == "codebuild:StartBuild"

    def test_empty_reason(self) -> None:
        r = parse_reason("")
        assert r.action == "UNKNOWN"
        assert r.confidence == "LOW"

    def test_unrecognized_reason(self) -> None:
        r = parse_reason("some completely novel mechanism")
        assert r.action == "UNKNOWN"
        assert r.confidence == "LOW"

    def test_preserves_raw(self) -> None:
        raw = "can call sts:AssumeRole to access"
        r = parse_reason(raw)
        assert r.raw == raw


# ===================================================================
# PMapper Graph Loader
# ===================================================================


class TestLoadPMapperGraph:
    def test_load_from_json(self) -> None:
        g = load_pmapper_graph(FIXTURE)
        assert len(g.nodes) == 9
        assert len(g.edges) == 12
        assert g.metadata["account_id"] == "111111111111"

    def test_nodes_have_arns(self) -> None:
        g = load_pmapper_graph(FIXTURE)
        for n in g.nodes:
            assert n.arn.startswith("arn:aws:")

    def test_edges_have_source_destination(self) -> None:
        g = load_pmapper_graph(FIXTURE)
        for e in g.edges:
            assert e.source.startswith("arn:aws:")
            assert e.destination.startswith("arn:aws:")
            assert len(e.reason) > 0

    def test_admin_detected(self) -> None:
        g = load_pmapper_graph(FIXTURE)
        admins = [n for n in g.nodes if n.is_admin]
        assert len(admins) == 2  # ProdAdmin and SharedAdmin

    def test_trust_policies_preserved(self) -> None:
        g = load_pmapper_graph(FIXTURE)
        roles_with_trust = [n for n in g.nodes if n.trust_policy]
        assert len(roles_with_trust) == 8

    def test_invalid_file_raises(self) -> None:
        with pytest.raises(ARFValidationError):
            load_pmapper_graph("/nonexistent/path.json")


# ===================================================================
# PMapper Graph Translation
# ===================================================================


class TestTranslatePMapperGraph:
    def test_translate_node_count(self) -> None:
        result = translate_from_file(FIXTURE)
        assert result.node_count == 9

    def test_translate_edge_count(self) -> None:
        result = translate_from_file(FIXTURE)
        assert result.edge_count == 12

    def test_nodes_have_arf_format(self) -> None:
        result = translate_from_file(FIXTURE)
        for n in result.nodes:
            assert n["provider"] == "aws"
            assert n["node_type"] in (
                "IAMRole", "IAMUser", "IAMGroup", "LambdaFunction",
                "EC2Instance", "S3Bucket",
            )
            assert n["provider_id"].startswith("arn:aws:")
            assert "region" in n

    def test_edges_have_arf_format(self) -> None:
        result = translate_from_file(FIXTURE)
        for e in result.edges:
            assert "edge_type" in e
            assert "src" in e and "dst" in e
            assert "features" in e
            assert e["src"]["provider"] == "aws"
            assert e["dst"]["provider"] == "aws"
            assert "action" in e["features"]

    def test_action_summary(self) -> None:
        result = translate_from_file(FIXTURE)
        summary = result.action_summary
        assert "sts:AssumeRole" in summary
        assert summary["sts:AssumeRole"] >= 5  # multiple AssumeRole edges
        assert "ADMIN_ACCESS" in summary
        assert "lambda:UpdateFunctionCode" in summary

    def test_trust_policies_extracted(self) -> None:
        result = translate_from_file(FIXTURE)
        assert len(result.trust_policies) == 8

    def test_admin_arns_tracked(self) -> None:
        result = translate_from_file(FIXTURE)
        assert len(result.admin_arns) == 2
        assert any("ProdAdmin" in a for a in result.admin_arns)
        assert any("SharedAdmin" in a for a in result.admin_arns)

    def test_account_id_from_metadata(self) -> None:
        result = translate_from_file(FIXTURE)
        assert result.account_id == "111111111111"

    def test_cross_account_edges_preserved(self) -> None:
        """DevOps (111) → ProdAdmin (222) should produce a cross-account edge."""
        result = translate_from_file(FIXTURE)
        cross = [
            e for e in result.edges
            if "111111111111" in e["src"]["provider_id"]
            and "222222222222" in e["dst"]["provider_id"]
        ]
        assert len(cross) >= 1

    def test_diverse_mechanisms(self) -> None:
        """Fixture has direct_call, admin, ec2, lambda mechanisms."""
        result = translate_from_file(FIXTURE)
        mechanisms = {e["features"]["mechanism"] for e in result.edges}
        assert "direct_call" in mechanisms
        assert "admin" in mechanisms
        assert "ec2" in mechanisms
        assert "lambda" in mechanisms

    def test_no_warnings_for_clean_fixture(self) -> None:
        """All edges reference nodes that exist in the graph."""
        result = translate_from_file(FIXTURE)
        auto_create_warnings = [
            w for w in result.warnings if "auto-creating" in w
        ]
        assert len(auto_create_warnings) == 0


class TestTranslateEdgeCases:
    def test_missing_node_auto_created(self) -> None:
        """Edge referencing unknown node → auto-create + warning."""
        from arf_rt.adapters.pmapper import PMapperGraph, translate_pmapper_graph

        graph = PMapperGraph(
            nodes=[{"arn": "arn:aws:iam::123456789012:role/A"}],
            edges=[{
                "source": "arn:aws:iam::123456789012:role/A",
                "destination": "arn:aws:iam::123456789012:role/Phantom",
                "reason": "can call sts:AssumeRole to access",
            }],
        )
        result = translate_pmapper_graph(graph)
        assert result.node_count == 2  # A + auto-created Phantom
        assert any("auto-creating" in w for w in result.warnings)

    def test_invalid_node_arn_skipped(self) -> None:
        from arf_rt.adapters.pmapper import PMapperGraph, translate_pmapper_graph

        graph = PMapperGraph(
            nodes=[
                {"arn": "arn:aws:iam::123456789012:role/Good"},
                {"arn": "not-a-valid-arn"},
            ],
            edges=[],
        )
        result = translate_pmapper_graph(graph)
        assert result.node_count == 1  # only Good
        assert any("invalid ARN" in w.lower() or "Invalid" in w for w in result.warnings)

    def test_empty_graph(self) -> None:
        from arf_rt.adapters.pmapper import PMapperGraph, translate_pmapper_graph

        graph = PMapperGraph(nodes=[], edges=[])
        result = translate_pmapper_graph(graph)
        assert result.node_count == 0
        assert result.edge_count == 0

    def test_duplicate_nodes_handled(self) -> None:
        """PMapper might have duplicate ARNs — should not crash."""
        from arf_rt.adapters.pmapper import PMapperGraph, translate_pmapper_graph

        graph = PMapperGraph(
            nodes=[
                {"arn": "arn:aws:iam::123456789012:role/R"},
                {"arn": "arn:aws:iam::123456789012:role/R"},
            ],
            edges=[],
        )
        result = translate_pmapper_graph(graph)
        # Both appear in nodes list (dedup is replay adapter's job)
        assert result.node_count == 2
