"""Input hardening tests (Session 10).

Tests for security and robustness of input validation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arf_rt.adapters.seed_json import (
    MAX_SCENARIO_SIZE_BYTES,
    load_scenario_file,
    load_scenario_string,
)
from arf_rt.util.canon import ARFValidationError


class TestOversizedScenario:
    def test_rejects_oversized_file(self, tmp_path) -> None:
        big = tmp_path / "big.json"
        big.write_bytes(b"x" * (MAX_SCENARIO_SIZE_BYTES + 1))
        with pytest.raises(ARFValidationError, match="too large"):
            load_scenario_file(big)


class TestExtraFieldsRejected:
    def test_extra_top_level_field_rejected(self) -> None:
        raw = json.dumps({
            "nodes": [{"provider": "aws", "node_type": "IAMRole",
                        "provider_id": "r1", "region": "us-east-1"}],
            "edges": [{"edge_type": "test", "src": "r1", "dst": "r1",
                        "features": {"a": "b"}}],
            "objectives": [{"objective_type": "REACHABILITY",
                             "start_nodes": ["r1"], "target_nodes": ["r1"],
                             "max_depth": 3, "k": 3}],
            "MALICIOUS_EXTRA_FIELD": "should_be_rejected",
        })
        with pytest.raises(ARFValidationError, match="Extra inputs"):
            load_scenario_string(raw)

    def test_extra_node_field_rejected(self) -> None:
        raw = json.dumps({
            "nodes": [{"provider": "aws", "node_type": "IAMRole",
                        "provider_id": "r1", "region": "us-east-1",
                        "EXTRA": "bad"}],
            "edges": [],
            "objectives": [{"objective_type": "REACHABILITY",
                             "start_nodes": ["r1"], "target_nodes": ["r1"],
                             "max_depth": 3, "k": 3}],
        })
        with pytest.raises(ARFValidationError, match="Extra inputs"):
            load_scenario_string(raw)


class TestUnknownEnums:
    def test_unknown_observation_strength_rejected(self) -> None:
        raw = json.dumps({
            "nodes": [{"provider": "aws", "node_type": "IAMRole",
                        "provider_id": "r1", "region": "us-east-1"}],
            "edges": [{"edge_type": "test", "src": "r1", "dst": "r1",
                        "features": {"a": "b"}}],
            "objectives": [{"objective_type": "REACHABILITY",
                             "start_nodes": ["r1"], "target_nodes": ["r1"],
                             "max_depth": 3, "k": 3}],
            "observations": [{"edge_ref": "r1", "probe_type": "REPLAY_SCRIPTED",
                               "result": "ALLOW", "reason_class": "UNKNOWN",
                               "strength": "BOGUS_STRENGTH", "signal_q": 80}],
        })
        with pytest.raises(ARFValidationError, match="BOGUS_STRENGTH"):
            load_scenario_string(raw)

    def test_unknown_observation_result_rejected(self) -> None:
        raw = json.dumps({
            "nodes": [{"provider": "aws", "node_type": "IAMRole",
                        "provider_id": "r1", "region": "us-east-1"}],
            "edges": [{"edge_type": "test", "src": "r1", "dst": "r1",
                        "features": {"a": "b"}}],
            "objectives": [{"objective_type": "REACHABILITY",
                             "start_nodes": ["r1"], "target_nodes": ["r1"],
                             "max_depth": 3, "k": 3}],
            "observations": [{"edge_ref": "r1", "probe_type": "REPLAY_SCRIPTED",
                               "result": "BOGUS_RESULT", "reason_class": "UNKNOWN",
                               "strength": "DIRECT", "signal_q": 80}],
        })
        with pytest.raises(ARFValidationError, match="BOGUS_RESULT"):
            load_scenario_string(raw)


class TestMalformedInput:
    def test_invalid_json_rejected(self) -> None:
        with pytest.raises(ARFValidationError, match="JSON"):
            load_scenario_string("{not valid json")

    def test_empty_object_rejected(self) -> None:
        with pytest.raises(ARFValidationError):
            load_scenario_string("{}")

    def test_signal_q_out_of_range_rejected(self) -> None:
        raw = json.dumps({
            "nodes": [{"provider": "aws", "node_type": "IAMRole",
                        "provider_id": "r1", "region": "us-east-1"}],
            "edges": [{"edge_type": "test", "src": "r1", "dst": "r1",
                        "features": {"a": "b"}}],
            "objectives": [{"objective_type": "REACHABILITY",
                             "start_nodes": ["r1"], "target_nodes": ["r1"],
                             "max_depth": 3, "k": 3}],
            "observations": [{"edge_ref": "r1", "probe_type": "REPLAY_SCRIPTED",
                               "result": "ALLOW", "reason_class": "UNKNOWN",
                               "strength": "DIRECT", "signal_q": 150}],
        })
        with pytest.raises(ARFValidationError, match="signal_q"):
            load_scenario_string(raw)

    def test_negative_signal_q_rejected(self) -> None:
        raw = json.dumps({
            "nodes": [{"provider": "aws", "node_type": "IAMRole",
                        "provider_id": "r1", "region": "us-east-1"}],
            "edges": [{"edge_type": "test", "src": "r1", "dst": "r1",
                        "features": {"a": "b"}}],
            "objectives": [{"objective_type": "REACHABILITY",
                             "start_nodes": ["r1"], "target_nodes": ["r1"],
                             "max_depth": 3, "k": 3}],
            "observations": [{"edge_ref": "r1", "probe_type": "REPLAY_SCRIPTED",
                               "result": "ALLOW", "reason_class": "UNKNOWN",
                               "strength": "DIRECT", "signal_q": -1}],
        })
        with pytest.raises(ARFValidationError, match="signal_q"):
            load_scenario_string(raw)

    def test_no_objectives_rejected(self) -> None:
        raw = json.dumps({
            "nodes": [{"provider": "aws", "node_type": "IAMRole",
                        "provider_id": "r1", "region": "us-east-1"}],
            "edges": [],
            "objectives": [],
        })
        with pytest.raises(ARFValidationError, match="[Oo]bjective"):
            load_scenario_string(raw)


class TestCLIIntegration:
    def test_cli_hash_deterministic(self) -> None:
        from arf_rt.cli import main
        import io
        import sys

        old_stdout = sys.stdout
        results = []
        for _ in range(3):
            sys.stdout = io.StringIO()
            try:
                main(["hash", str(Path(__file__).parent.parent / "fixtures" / "minimal_scenario.json")])
                results.append(sys.stdout.getvalue().strip())
            finally:
                sys.stdout = old_stdout

        assert len(set(results)) == 1
