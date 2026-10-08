"""Golden Top-K tests: exact expected values for minimal scenario.

These tests pin the exact output of the full pipeline. If any of these
break, a determinism regression has occurred.
"""

from __future__ import annotations

import json
from pathlib import Path

from arf_rt.cli import run_full_pipeline
from arf_rt.engine.snapshot import canonical_run_hash
from arf_rt.reporting.json_output import generate_json_output


SCENARIO = str(Path(__file__).parent.parent / "fixtures" / "minimal_scenario.json")

# --- Pinned golden values ---
GOLDEN_HASH = "550dc819fec5853785e4fc9c1be08276d3e3a7371d4754904e7241caaa1c2915"
GOLDEN_EDGE_AB = "040335e14a03fb40e5fac4e0bf77bb1d7522f141730e574948a493c87eb9030d"
GOLDEN_EDGE_BC = "0c29947a76e5f171326776c8a6094274bb627882e6d43ee7b313e42f69284f60"
GOLDEN_EDGE_SEQ = [GOLDEN_EDGE_AB, GOLDEN_EDGE_BC]
GOLDEN_P_WORST_Q8 = 1139846
GOLDEN_P_BEST_Q8 = 1139846
GOLDEN_BAND = "VERY_LOW"
GOLDEN_PATH_LEN = 2
GOLDEN_COVERAGE_PCT = 100


class TestGoldenCanonicalHash:
    def test_exact_hash(self) -> None:
        conn, _ = run_full_pipeline(SCENARIO)
        assert canonical_run_hash(conn) == GOLDEN_HASH

    def test_hash_stable_10_runs(self) -> None:
        hashes = set()
        for _ in range(10):
            conn, _ = run_full_pipeline(SCENARIO)
            hashes.add(canonical_run_hash(conn))
        assert len(hashes) == 1
        assert hashes.pop() == GOLDEN_HASH

    def test_reporting_output_deterministic(self) -> None:
        """Hash covers state but not rendered output — verify reports too."""
        from arf_rt.reporting.markdown_report import generate_markdown_report
        from arf_rt.reporting.json_output import generate_json_output
        import json
        mds, jsons = set(), set()
        for _ in range(5):
            conn, _ = run_full_pipeline(SCENARIO)
            mds.add(generate_markdown_report(conn))
            jsons.add(json.dumps(generate_json_output(conn), sort_keys=True))
        assert len(mds) == 1, "Markdown output not deterministic"
        assert len(jsons) == 1, "JSON output not deterministic"


class TestGoldenTopK:
    def test_exact_edge_sequence(self) -> None:
        conn, _ = run_full_pipeline(SCENARIO)
        output = generate_json_output(conn)
        path = output["objectives"][0]["paths"][0]
        assert path["edge_id_sequence"] == GOLDEN_EDGE_SEQ

    def test_exact_p_worst_q8(self) -> None:
        conn, _ = run_full_pipeline(SCENARIO)
        output = generate_json_output(conn)
        path = output["objectives"][0]["paths"][0]
        assert path["p_worst_q8"] == GOLDEN_P_WORST_Q8

    def test_exact_p_best_q8(self) -> None:
        conn, _ = run_full_pipeline(SCENARIO)
        output = generate_json_output(conn)
        path = output["objectives"][0]["paths"][0]
        assert path["p_best_q8"] == GOLDEN_P_BEST_Q8

    def test_exact_confidence_band(self) -> None:
        conn, _ = run_full_pipeline(SCENARIO)
        output = generate_json_output(conn)
        path = output["objectives"][0]["paths"][0]
        assert path["confidence_band"] == GOLDEN_BAND

    def test_exact_path_length(self) -> None:
        conn, _ = run_full_pipeline(SCENARIO)
        output = generate_json_output(conn)
        path = output["objectives"][0]["paths"][0]
        assert path["path_length"] == GOLDEN_PATH_LEN

    def test_exact_evidence_coverage(self) -> None:
        conn, _ = run_full_pipeline(SCENARIO)
        output = generate_json_output(conn)
        assert output["evidence_coverage"]["coverage_percent"] == GOLDEN_COVERAGE_PCT

    def test_single_path_found(self) -> None:
        conn, _ = run_full_pipeline(SCENARIO)
        output = generate_json_output(conn)
        assert len(output["objectives"][0]["paths"]) == 1

    def test_path_flags_clean(self) -> None:
        conn, _ = run_full_pipeline(SCENARIO)
        output = generate_json_output(conn)
        flags = output["objectives"][0]["paths"][0]["flags"]
        assert flags["conflict"] is False
        assert flags["prior_only"] is False
        assert flags["counterfactual_override"] is False
