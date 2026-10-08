"""Golden what-if tests: exact ROI line and diff values for minimal scenario."""

from __future__ import annotations

from pathlib import Path

from arf_rt.cli import run_full_pipeline
from arf_rt.engine.whatif import run_whatif


SCENARIO = str(Path(__file__).parent.parent / "fixtures" / "minimal_scenario.json")

GOLDEN_EDGE_AB = "040335e14a03fb40e5fac4e0bf77bb1d7522f141730e574948a493c87eb9030d"
GOLDEN_BASELINE_HASH = "550dc819fec5853785e4fc9c1be08276d3e3a7371d4754904e7241caaa1c2915"
GOLDEN_FORK_HASH = "45fc746351f7e803b3233b76796cbc8bbd97ff2ab6282e824fbe0ea484e582ba"
GOLDEN_ROI_LINE = (
    "Control ROI: 0 of Top-K paths removed (0%), "
    "highest remaining path confidence: Insufficient, "
    "evidence coverage: 100% of edges observed."
)


def _run_whatif():
    conn, _ = run_full_pipeline(SCENARIO)
    return run_whatif(conn, [GOLDEN_EDGE_AB])


class TestGoldenROI:
    def test_exact_roi_line(self) -> None:
        result = _run_whatif()
        assert result["diff_report"]["control_roi_line"] == GOLDEN_ROI_LINE

    def test_roi_line_stable(self) -> None:
        lines = set()
        for _ in range(3):
            result = _run_whatif()
            lines.add(result["diff_report"]["control_roi_line"])
        assert len(lines) == 1


class TestGoldenDiff:
    def test_baseline_hash_matches(self) -> None:
        result = _run_whatif()
        assert result["baseline_hash"] == GOLDEN_BASELINE_HASH

    def test_fork_hash_matches(self) -> None:
        result = _run_whatif()
        assert result["fork_hash"] == GOLDEN_FORK_HASH

    def test_baseline_verified(self) -> None:
        result = _run_whatif()
        assert result["baseline_verified"] is True

    def test_paths_removed_count(self) -> None:
        result = _run_whatif()
        assert result["diff_report"]["paths_removed"] == 0

    def test_edge_diffs_count(self) -> None:
        result = _run_whatif()
        assert len(result["diff_report"]["edge_diffs"]) == 1

    def test_edge_diff_is_belief_changed(self) -> None:
        result = _run_whatif()
        diff = result["diff_report"]["edge_diffs"][0]
        assert diff["change"] == "belief_changed"
        assert diff["edge_id"] == GOLDEN_EDGE_AB

    def test_fork_hash_stable(self) -> None:
        hashes = set()
        for _ in range(3):
            result = _run_whatif()
            hashes.add(result["fork_hash"])
        assert len(hashes) == 1

    def test_diff_ordering_deterministic(self) -> None:
        """Edge diffs in same order across runs."""
        diffs = []
        for _ in range(3):
            result = _run_whatif()
            diffs.append(
                [(d["edge_id"], d["change"]) for d in result["diff_report"]["edge_diffs"]]
            )
        for d in diffs[1:]:
            assert d == diffs[0]
