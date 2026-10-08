"""Tests for engine/templates.py (spec §11)."""

from __future__ import annotations

import pytest

from arf_rt.config import MAX_TEMPLATE_MASS
from arf_rt.engine.templates import aggregate_to_template
from arf_rt.storage.sqlite_store import connect
from arf_rt.storage.migrations import run_migrations
from arf_rt.util.canon import canonical_json, features_fp, make_template_id, make_template_key


def _setup_template_db(alpha=1, beta=1):
    """Create a DB with one template."""
    conn = connect(":memory:")

    feat = {"action": "test"}
    feat_fp = features_fp(feat)
    tpl_id = make_template_id("aws", "test_type", feat_fp, 1)
    tpl_key = make_template_key("aws", "test_type", feat_fp)

    conn.execute(
        """INSERT INTO templates
           (template_id, template_key, provider, edge_type,
            features_json, features_fp, feature_schema_version,
            alpha_agg_i, beta_agg_i, sample_count)
           VALUES (?, ?, 'aws', 'test_type', ?, ?, 1, ?, ?, 0)""",
        (tpl_id, tpl_key, canonical_json(feat), feat_fp, alpha, beta),
    )
    conn.commit()
    return conn, tpl_id


class TestAggregateToTemplate:
    def test_support_increases_alpha(self) -> None:
        conn, tpl_id = _setup_template_db()
        aggregate_to_template(conn, tpl_id, "SUPPORT", 76)
        conn.commit()

        row = conn.execute(
            "SELECT alpha_agg_i, beta_agg_i, sample_count FROM templates"
        ).fetchone()
        assert row["alpha_agg_i"] == 1 + 76
        assert row["beta_agg_i"] == 1
        assert row["sample_count"] == 1

    def test_against_increases_beta(self) -> None:
        conn, tpl_id = _setup_template_db()
        aggregate_to_template(conn, tpl_id, "AGAINST", 85)
        conn.commit()

        row = conn.execute("SELECT alpha_agg_i, beta_agg_i FROM templates").fetchone()
        assert row["alpha_agg_i"] == 1
        assert row["beta_agg_i"] == 1 + 85

    def test_neutral_no_op(self) -> None:
        conn, tpl_id = _setup_template_db()
        aggregate_to_template(conn, tpl_id, "NEUTRAL", 50)
        conn.commit()

        row = conn.execute("SELECT alpha_agg_i, beta_agg_i, sample_count FROM templates").fetchone()
        assert row["alpha_agg_i"] == 1
        assert row["beta_agg_i"] == 1
        assert row["sample_count"] == 0

    def test_zero_increment_no_op(self) -> None:
        conn, tpl_id = _setup_template_db()
        aggregate_to_template(conn, tpl_id, "SUPPORT", 0)
        conn.commit()

        row = conn.execute("SELECT alpha_agg_i, sample_count FROM templates").fetchone()
        assert row["alpha_agg_i"] == 1
        assert row["sample_count"] == 0

    def test_mass_cap_applied(self) -> None:
        """Template mass cap = 200000."""
        conn, tpl_id = _setup_template_db(alpha=150000, beta=40000)
        # mass = 190000, add 20000 → 210000 > 200000
        aggregate_to_template(conn, tpl_id, "SUPPORT", 20000)
        conn.commit()

        row = conn.execute("SELECT alpha_agg_i, beta_agg_i FROM templates").fetchone()
        total = row["alpha_agg_i"] + row["beta_agg_i"]
        assert total == MAX_TEMPLATE_MASS

    def test_sample_count_increments(self) -> None:
        conn, tpl_id = _setup_template_db()
        aggregate_to_template(conn, tpl_id, "SUPPORT", 10)
        aggregate_to_template(conn, tpl_id, "AGAINST", 20)
        conn.commit()

        row = conn.execute("SELECT sample_count FROM templates").fetchone()
        assert row["sample_count"] == 2
