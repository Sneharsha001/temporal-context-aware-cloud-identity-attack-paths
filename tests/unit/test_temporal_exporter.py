"""
tests/unit/test_temporal_exporter.py - Unit tests for TemporalExporter.

Validates JSON, NDJSON, and CSV serialisation of TemporalHint and
CredentialRiskScore collections, including summary export format and
round-trip parsability.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

import pytest

from arf_rt.temporal.credential_scorer import CredentialRiskScore
from arf_rt.temporal.hints import TemporalHint
from arf_rt.temporal.temporal_exporter import TemporalExporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc)


def _hint(edge_id: str = "e1") -> TemporalHint:
    return TemporalHint(
        edge_id=edge_id,
        credential_expiry=NOW,
        last_used=NOW,
    )


def _score(edge_id: str = "e1", score: float = 0.75) -> CredentialRiskScore:
    return CredentialRiskScore(
        edge_id=edge_id,
        score=score,
        expiry_factor=0.8,
        staleness_factor=0.6,
        short_lived_bonus=0.0,
    )


# ---------------------------------------------------------------------------
# hints_to_json
# ---------------------------------------------------------------------------

class TestHintsToJson:
    def test_returns_valid_json(self):
        exporter = TemporalExporter()
        output = exporter.hints_to_json([_hint()])
        parsed = json.loads(output)
        assert isinstance(parsed, list)

    def test_single_hint_in_array(self):
        exporter = TemporalExporter()
        output = exporter.hints_to_json([_hint("edge-42")])
        parsed = json.loads(output)
        assert len(parsed) == 1
        assert parsed[0]["edge_id"] == "edge-42"

    def test_multiple_hints(self):
        exporter = TemporalExporter()
        hints = [_hint("a"), _hint("b"), _hint("c")]
        parsed = json.loads(exporter.hints_to_json(hints))
        assert len(parsed) == 3

    def test_empty_hints_returns_empty_array(self):
        exporter = TemporalExporter()
        parsed = json.loads(exporter.hints_to_json([]))
        assert parsed == []

    def test_datetime_fields_are_iso_strings(self):
        exporter = TemporalExporter()
        parsed = json.loads(exporter.hints_to_json([_hint()]))
        record = parsed[0]
        assert isinstance(record["credential_expiry"], str)
        assert "2026" in record["credential_expiry"]

    def test_none_fields_serialised_as_null(self):
        exporter = TemporalExporter()
        hint = TemporalHint(edge_id="bare")
        parsed = json.loads(exporter.hints_to_json([hint]))
        assert parsed[0]["credential_expiry"] is None

    def test_custom_indent(self):
        exporter = TemporalExporter()
        output = exporter.hints_to_json([_hint()], indent=4)
        assert "    " in output  # 4-space indent


# ---------------------------------------------------------------------------
# hints_to_ndjson
# ---------------------------------------------------------------------------

class TestHintsToNdjson:
    def test_one_line_per_hint(self):
        exporter = TemporalExporter()
        output = exporter.hints_to_ndjson([_hint("a"), _hint("b")])
        lines = output.strip().split("\n")
        assert len(lines) == 2

    def test_each_line_is_valid_json(self):
        exporter = TemporalExporter()
        output = exporter.hints_to_ndjson([_hint("x"), _hint("y")])
        for line in output.strip().split("\n"):
            obj = json.loads(line)
            assert "edge_id" in obj

    def test_empty_list_returns_empty_string(self):
        exporter = TemporalExporter()
        assert exporter.hints_to_ndjson([]) == ""


# ---------------------------------------------------------------------------
# hints_to_csv
# ---------------------------------------------------------------------------

class TestHintsToCsv:
    def test_has_header_row(self):
        exporter = TemporalExporter()
        output = exporter.hints_to_csv([_hint()])
        reader = csv.DictReader(io.StringIO(output))
        assert "edge_id" in reader.fieldnames

    def test_correct_row_count(self):
        exporter = TemporalExporter()
        output = exporter.hints_to_csv([_hint("a"), _hint("b"), _hint("c")])
        reader = csv.DictReader(io.StringIO(output))
        rows = list(reader)
        assert len(rows) == 3

    def test_edge_id_in_row(self):
        exporter = TemporalExporter()
        output = exporter.hints_to_csv([_hint("my-edge")])
        reader = csv.DictReader(io.StringIO(output))
        row = next(reader)
        assert row["edge_id"] == "my-edge"

    def test_empty_hints_only_header(self):
        exporter = TemporalExporter()
        output = exporter.hints_to_csv([])
        reader = csv.DictReader(io.StringIO(output))
        rows = list(reader)
        assert rows == []


# ---------------------------------------------------------------------------
# scores_to_json
# ---------------------------------------------------------------------------

class TestScoresToJson:
    def test_returns_valid_json(self):
        exporter = TemporalExporter()
        output = exporter.scores_to_json([_score()])
        parsed = json.loads(output)
        assert isinstance(parsed, list)

    def test_score_fields_present(self):
        exporter = TemporalExporter()
        parsed = json.loads(exporter.scores_to_json([_score("edge-1", 0.80)]))
        rec = parsed[0]
        for field in ("edge_id", "score", "label", "expiry_factor", "staleness_factor", "short_lived_bonus"):
            assert field in rec

    def test_label_set_correctly(self):
        exporter = TemporalExporter()
        parsed = json.loads(exporter.scores_to_json([_score("e", 0.85)]))
        assert parsed[0]["label"] == "CRITICAL"

    def test_empty_scores_returns_empty_array(self):
        exporter = TemporalExporter()
        parsed = json.loads(exporter.scores_to_json([]))
        assert parsed == []


# ---------------------------------------------------------------------------
# scores_to_ndjson
# ---------------------------------------------------------------------------

class TestScoresToNdjson:
    def test_one_line_per_score(self):
        exporter = TemporalExporter()
        output = exporter.scores_to_ndjson([_score("a"), _score("b")])
        lines = output.strip().split("\n")
        assert len(lines) == 2

    def test_each_line_has_edge_id(self):
        exporter = TemporalExporter()
        output = exporter.scores_to_ndjson([_score("z")])
        obj = json.loads(output.strip())
        assert obj["edge_id"] == "z"


# ---------------------------------------------------------------------------
# scores_to_csv
# ---------------------------------------------------------------------------

class TestScoresToCsv:
    def test_has_header_and_row(self):
        exporter = TemporalExporter()
        output = exporter.scores_to_csv([_score("e", 0.5)])
        reader = csv.DictReader(io.StringIO(output))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["edge_id"] == "e"

    def test_score_value_preserved(self):
        exporter = TemporalExporter()
        output = exporter.scores_to_csv([_score("e", 0.73)])
        reader = csv.DictReader(io.StringIO(output))
        row = next(reader)
        assert float(row["score"]) == pytest.approx(0.73)


# ---------------------------------------------------------------------------
# summary_json
# ---------------------------------------------------------------------------

class TestSummaryJson:
    def test_summary_parseable(self):
        exporter = TemporalExporter()
        output = exporter.summary_json([_hint()], [_score()])
        parsed = json.loads(output)
        assert "generated_at" in parsed

    def test_hint_and_score_counts(self):
        exporter = TemporalExporter()
        hints = [_hint("a"), _hint("b")]
        scores = [_score("a"), _score("b")]
        parsed = json.loads(exporter.summary_json(hints, scores))
        assert parsed["hint_count"] == 2
        assert parsed["score_count"] == 2

    def test_custom_generated_at(self):
        exporter = TemporalExporter()
        ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        parsed = json.loads(exporter.summary_json([], [], generated_at=ts))
        assert "2026-01-01" in parsed["generated_at"]

    def test_empty_summary(self):
        exporter = TemporalExporter()
        parsed = json.loads(exporter.summary_json([], []))
        assert parsed["hint_count"] == 0
        assert parsed["score_count"] == 0
        assert parsed["hints"] == []
        assert parsed["scores"] == []
