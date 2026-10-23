"""
arf_rt/temporal/batch_runner.py - Multi-scenario batch temporal feasibility runner.

Processes multiple scenario path sets concurrently or sequentially, aggregating
system-wide elimination rates, constraint violations, and per-scenario metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from arf_rt.temporal.audit_log import TemporalAuditLog
from arf_rt.temporal.config import TemporalConfig
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.metrics import TemporalMetrics
from arf_rt.temporal.path_filter import FilterResult, TemporalPathFilter


@dataclass
class ScenarioBatchResult:
    """Evaluation output for a single scenario within a multi-scenario batch."""
    scenario_id: str
    total_paths: int
    feasible_paths: int
    infeasible_paths: int
    unknown_paths: int
    elimination_rate: float
    filter_results: list[FilterResult]


class PathFeasibilityBatchRunner:
    """
    Executes temporal feasibility checks across multiple attack path scenarios,
    producing individual and aggregated diagnostic reports.
    """

    def __init__(
        self,
        config: TemporalConfig | None = None,
        reference_time: datetime | None = None,
    ) -> None:
        self.config = config or TemporalConfig()
        self.reference_time = reference_time
        self.path_filter = TemporalPathFilter(
            config=self.config,
            reference_time=self.reference_time,
            run_window_checks=True,
        )
        self.global_metrics = TemporalMetrics()
        self.scenario_results: dict[str, ScenarioBatchResult] = {}
        self.audit_log = TemporalAuditLog()

    def run_scenario(
        self,
        scenario_id: str,
        paths: list[list[str]],
        hints: dict[str, TemporalHint],
    ) -> ScenarioBatchResult:
        """Run temporal evaluation on candidate paths for a single scenario."""
        results = self.path_filter.filter(paths, hints)

        feas = 0
        inf = 0
        unk = 0

        for r in results:
            plen = len(r.edge_ids)
            if r.verdict_kind == "FEASIBLE":
                feas += 1
                self.global_metrics.record_feasible(plen)
            elif r.verdict_kind == "INFEASIBLE":
                inf += 1
                self.global_metrics.record_infeasible(r.rejected_by or "TC_VIOLATION", plen)
            else:
                unk += 1
                self.global_metrics.record_unknown(plen)

        total = len(paths)
        elim_rate = inf / max(1, total)

        batch_res = ScenarioBatchResult(
            scenario_id=scenario_id,
            total_paths=total,
            feasible_paths=feas,
            infeasible_paths=inf,
            unknown_paths=unk,
            elimination_rate=elim_rate,
            filter_results=results,
        )
        self.scenario_results[scenario_id] = batch_res
        return batch_res

    def run_all(
        self,
        scenarios: dict[str, tuple[list[list[str]], dict[str, TemporalHint]]],
    ) -> dict[str, ScenarioBatchResult]:
        """Run all provided scenarios and return mapping of scenario_id -> ScenarioBatchResult."""
        for sc_id, (paths, hints) in scenarios.items():
            self.run_scenario(sc_id, paths, hints)
        return self.scenario_results

    def generate_comparison_table(self) -> str:
        """Generate a Markdown ranking table comparing elimination rates across scenarios."""
        if not self.scenario_results:
            return "No scenarios evaluated."

        lines = [
            "| Scenario ID | Total Paths | Feasible | Infeasible | Unknown | Elimination Rate |",
            "|---|---|---|---|---|---|",
        ]

        # Rank by elimination rate descending
        sorted_scenarios = sorted(
            self.scenario_results.values(),
            key=lambda s: s.elimination_rate,
            reverse=True,
        )

        for s in sorted_scenarios:
            lines.append(
                f"| `{s.scenario_id}` | {s.total_paths} | {s.feasible_paths} | "
                f"{s.infeasible_paths} | {s.unknown_paths} | {s.elimination_rate:.1%} |"
            )

        return "\n".join(lines)
