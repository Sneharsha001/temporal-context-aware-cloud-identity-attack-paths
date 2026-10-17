"""
tests/unit/test_objective_helpers.py - Unit tests for scenario objective helpers.
"""

from arf_rt.util.objective_helpers import (
    validate_node_ref,
    build_reachability_objective,
)


def test_validate_node_ref_valid():
    valid_node = {"provider": "aws", "node_type": "IAMUser", "provider_id": "arn:aws:iam::1:user/alice"}
    assert validate_node_ref(valid_node) is True


def test_validate_node_ref_invalid():
    invalid_node = {"provider": "aws"}
    assert validate_node_ref(invalid_node) is False


def test_build_reachability_objective():
    obj = build_reachability_objective("arn:user/alice", "arn:role/admin", max_depth=5, k=3)
    assert obj["objective_type"] == "REACHABILITY"
    assert obj["max_depth"] == 5
    assert obj["k"] == 3
    assert obj["start_nodes"][0]["provider_id"] == "arn:user/alice"
    assert obj["target_nodes"][0]["provider_id"] == "arn:role/admin"
