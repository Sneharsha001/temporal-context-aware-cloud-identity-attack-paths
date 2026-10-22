"""
tests/unit/test_audit_log.py - Unit tests for arf_rt.temporal.audit_log.

Covers AuditEntry construction, TemporalAuditLog recording, filtering,
JSONL serialization, and summary stats.
"""

from __future__ import annotations

import json

import pytest

from arf_rt.temporal.audit_log import AuditEntry, TemporalAuditLog
from arf_rt.temporal.verdict import TemporalVerdict, VerdictKind


def _feasible() -> TemporalVerdict:
    return TemporalVerdict.feasible()


def _infeasible(cid: str = "TC-1") -> TemporalVerdict:
    return TemporalVerdict.infeasible(cid, f"{cid} was violated")


def _unknown() -> TemporalVerdict:
    return TemporalVerdict.unknown(frozenset({"TC-3", "TC-4"}))


class TestAuditEntry:
    def test_to_dict_contains_all_fields(self) -> None:
        log = TemporalAuditLog()
        entry = log.record(["e1", "e2"], _feasible())
        d = entry.to_dict()
        assert "logged_at" in d
        assert d["path_edge_ids"] == ["e1", "e2"]
        assert d["verdict_kind"] == "FEASIBLE"
        assert d["violated_constraint"] is None

    def test_to_json_is_valid_json(self) -> None:
        log = TemporalAuditLog()
        entry = log.record(["e1"], _infeasible("TC-2"))
        parsed = json.loads(entry.to_json())
        assert parsed["violated_constraint"] == "TC-2"

    def test_metadata_stored(self) -> None:
        log = TemporalAuditLog()
        entry = log.record(["e1"], _feasible(), metadata={"scenario": "s1"})
        assert entry.metadata["scenario"] == "s1"


class TestTemporalAuditLog:
    def test_initially_empty(self) -> None:
        log = TemporalAuditLog()
        assert len(log) == 0

    def test_record_increases_length(self) -> None:
        log = TemporalAuditLog()
        log.record(["e1"], _feasible())
        log.record(["e2"], _infeasible())
        assert len(log) == 2

    def test_feasible_entries_filtered(self) -> None:
        log = TemporalAuditLog()
        log.record(["e1"], _feasible())
        log.record(["e2"], _infeasible())
        log.record(["e3"], _unknown())
        assert len(log.feasible_entries()) == 1
        assert len(log.infeasible_entries()) == 1
        assert len(log.unknown_entries()) == 1

    def test_to_jsonl_has_correct_line_count(self) -> None:
        log = TemporalAuditLog()
        for i in range(5):
            log.record([f"e{i}"], _feasible())
        lines = log.to_jsonl().strip().split("\n")
        assert len(lines) == 5

    def test_each_jsonl_line_is_valid_json(self) -> None:
        log = TemporalAuditLog()
        log.record(["e1"], _infeasible("TC-3"))
        log.record(["e2"], _unknown())
        for line in log.to_jsonl().strip().split("\n"):
            obj = json.loads(line)
            assert "verdict_kind" in obj

    def test_summary_counts_correct(self) -> None:
        log = TemporalAuditLog()
        log.record(["e1"], _feasible())
        log.record(["e2"], _feasible())
        log.record(["e3"], _infeasible())
        log.record(["e4"], _unknown())
        s = log.summary()
        assert s["FEASIBLE"] == 2
        assert s["INFEASIBLE"] == 1
        assert s["UNKNOWN"] == 1
        assert s["total"] == 4

    def test_clear_resets_log(self) -> None:
        log = TemporalAuditLog()
        log.record(["e1"], _feasible())
        log.clear()
        assert len(log) == 0
        assert log.summary()["total"] == 0

    def test_iterable(self) -> None:
        log = TemporalAuditLog()
        log.record(["e1"], _feasible())
        log.record(["e2"], _feasible())
        entries = list(log)
        assert len(entries) == 2

    def test_missing_data_constraints_sorted(self) -> None:
        log = TemporalAuditLog()
        entry = log.record(["e1"], _unknown())
        assert entry.missing_data_constraints == sorted(["TC-3", "TC-4"])
