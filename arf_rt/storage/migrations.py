"""Database schema migrations for ARF-RT (spec §§6-7).

Provides idempotent migration runner with version tracking.
All TEXT columns in determinism-sensitive contexts use COLLATE BINARY.
All JSON columns must contain canonical_json() output at write time.

Tables:
  schema_version   — migration version tracking
  nodes            — identity graph nodes
  templates        — edge behavioral templates (aggregated beliefs)
  edges            — trust relationships between nodes
  constraints      — security controls (SCPs, permission boundaries, etc.)
  edge_constraints — many-to-many: edges ↔ constraints
  objectives       — analysis objectives (paths to find)
  observations     — evidence collected about edges
  edge_updates     — audit trail for belief updates (spec §7.8)
  run_warnings     — warnings generated during processing
  derived_topk     — computed top-K paths (populated by path search)
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Current schema version — increment when adding migrations
CURRENT_SCHEMA_VERSION: int = 2

# --- Migration DDL ---
# Each entry is (version, description, list_of_sql_statements).
# Migrations are applied in order. Each is idempotent via IF NOT EXISTS.

_MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "Initial schema",
        [
            # --- schema_version ---
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version     INTEGER NOT NULL,
                applied_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                description TEXT    NOT NULL DEFAULT ''
            )
            """,

            # --- nodes ---
            """
            CREATE TABLE IF NOT EXISTS nodes (
                node_id         TEXT NOT NULL PRIMARY KEY COLLATE BINARY,
                provider        TEXT NOT NULL COLLATE BINARY,
                node_type       TEXT NOT NULL COLLATE BINARY,
                provider_id     TEXT NOT NULL COLLATE BINARY,
                region          TEXT NOT NULL COLLATE BINARY,
                display_name    TEXT NOT NULL DEFAULT '' COLLATE BINARY,
                properties_json TEXT NOT NULL DEFAULT '{}',
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """,

            # --- templates ---
            """
            CREATE TABLE IF NOT EXISTS templates (
                template_id             TEXT    NOT NULL PRIMARY KEY COLLATE BINARY,
                template_key            TEXT    NOT NULL COLLATE BINARY,
                provider                TEXT    NOT NULL COLLATE BINARY,
                edge_type               TEXT    NOT NULL COLLATE BINARY,
                features_json           TEXT    NOT NULL DEFAULT '{}',
                features_fp             TEXT    NOT NULL COLLATE BINARY,
                feature_schema_version  INTEGER NOT NULL DEFAULT 1,
                alpha_agg_i             INTEGER NOT NULL DEFAULT 1,
                beta_agg_i              INTEGER NOT NULL DEFAULT 1,
                sample_count            INTEGER NOT NULL DEFAULT 0,
                created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_templates_key
                ON templates (template_key COLLATE BINARY)
            """,

            # --- edges ---
            """
            CREATE TABLE IF NOT EXISTS edges (
                edge_id         TEXT    NOT NULL PRIMARY KEY COLLATE BINARY,
                edge_type       TEXT    NOT NULL COLLATE BINARY,
                src_node_id     TEXT    NOT NULL COLLATE BINARY
                                    REFERENCES nodes(node_id),
                dst_node_id     TEXT    NOT NULL COLLATE BINARY
                                    REFERENCES nodes(node_id),
                region          TEXT    NOT NULL COLLATE BINARY,
                template_id     TEXT    NOT NULL COLLATE BINARY
                                    REFERENCES templates(template_id),
                alpha_i         INTEGER NOT NULL DEFAULT 1,
                beta_i          INTEGER NOT NULL DEFAULT 1,
                status          TEXT    NOT NULL DEFAULT 'HYPOTHESIZED'
                                    COLLATE BINARY
                                    CHECK(status IN (
                                        'HYPOTHESIZED','CONFIRMED',
                                        'REFUTED','UNKNOWN_CONDITION'
                                    )),
                frozen          INTEGER NOT NULL DEFAULT 0
                                    CHECK(frozen IN (0, 1)),
                flags_json      TEXT    NOT NULL
                                    DEFAULT '{"conflict":false,"counterfactual_override":false,"prior_only":false,"stale":false}',
                features_json   TEXT    NOT NULL DEFAULT '{}',
                features_fp     TEXT    NOT NULL COLLATE BINARY,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_edges_src
                ON edges (src_node_id COLLATE BINARY)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_edges_dst
                ON edges (dst_node_id COLLATE BINARY)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_edges_template
                ON edges (template_id COLLATE BINARY)
            """,

            # --- constraints ---
            """
            CREATE TABLE IF NOT EXISTS constraints (
                constraint_id       TEXT NOT NULL PRIMARY KEY COLLATE BINARY,
                constraint_key      TEXT NOT NULL COLLATE BINARY,
                provider            TEXT NOT NULL COLLATE BINARY,
                constraint_type     TEXT NOT NULL COLLATE BINARY
                                        CHECK(constraint_type IN (
                                            'SCP','PERMISSION_BOUNDARY',
                                            'TRUST_CONDITION','RESOURCE_POLICY',
                                            'AZURE_CA','AZURE_PIM'
                                        )),
                scope_type          TEXT NOT NULL COLLATE BINARY,
                scope_id            TEXT NOT NULL COLLATE BINARY,
                region              TEXT NOT NULL COLLATE BINARY,
                properties_json     TEXT NOT NULL DEFAULT '{}',
                properties_fp       TEXT NOT NULL COLLATE BINARY,
                status              TEXT NOT NULL DEFAULT 'ACTIVE'
                                        COLLATE BINARY
                                        CHECK(status IN ('ACTIVE','INVALIDATED')),
                validation_status   TEXT NOT NULL DEFAULT 'UNVALIDATED'
                                        COLLATE BINARY
                                        CHECK(validation_status IN (
                                            'UNVALIDATED','VALIDATED','ASSUMED'
                                        )),
                confidence_q        INTEGER NOT NULL DEFAULT 0
                                        CHECK(confidence_q >= 0 AND confidence_q <= 1000),
                created_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_constraints_key
                ON constraints (constraint_key COLLATE BINARY)
            """,

            # --- edge_constraints ---
            """
            CREATE TABLE IF NOT EXISTS edge_constraints (
                edge_id         TEXT NOT NULL COLLATE BINARY
                                    REFERENCES edges(edge_id),
                constraint_id   TEXT NOT NULL COLLATE BINARY
                                    REFERENCES constraints(constraint_id),
                relation_type   TEXT NOT NULL DEFAULT 'APPLIES_TO'
                                    COLLATE BINARY
                                    CHECK(relation_type IN (
                                        'APPLIES_TO','DEPENDS_ON'
                                    )),
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (edge_id, constraint_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_ec_constraint
                ON edge_constraints (constraint_id COLLATE BINARY)
            """,

            # --- objectives ---
            """
            CREATE TABLE IF NOT EXISTS objectives (
                objective_id    TEXT    NOT NULL PRIMARY KEY COLLATE BINARY,
                objective_type  TEXT    NOT NULL COLLATE BINARY,
                start_nodes_json TEXT   NOT NULL,
                target_nodes_json TEXT  NOT NULL,
                max_depth       INTEGER NOT NULL CHECK(max_depth > 0),
                k               INTEGER NOT NULL CHECK(k > 0),
                created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """,

            # --- observations ---
            """
            CREATE TABLE IF NOT EXISTS observations (
                observation_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                edge_id             TEXT    NOT NULL COLLATE BINARY
                                        REFERENCES edges(edge_id),
                probe_type          TEXT    NOT NULL COLLATE BINARY
                                        CHECK(probe_type IN (
                                            'REPLAY_SCRIPTED','WHATIF_FORCED'
                                        )),
                result              TEXT    NOT NULL COLLATE BINARY
                                        CHECK(result IN (
                                            'ALLOW','DENY','ERROR','INCONCLUSIVE'
                                        )),
                reason_class        TEXT    NOT NULL COLLATE BINARY
                                        CHECK(reason_class IN (
                                            'CONSTRAINT_DENY','MISSING_PERMISSION',
                                            'CONDITION_MISMATCH','TRANSIENT',
                                            'THROTTLED','UNKNOWN'
                                        )),
                strength            TEXT    NOT NULL COLLATE BINARY
                                        CHECK(strength IN (
                                            'DETERMINISTIC','DIRECT',
                                            'INFERRED','HEURISTIC'
                                        )),
                signal_q            INTEGER NOT NULL
                                        CHECK(signal_q >= 0 AND signal_q <= 100),
                is_counterfactual   INTEGER NOT NULL DEFAULT 0
                                        CHECK(is_counterfactual IN (0, 1)),
                constraint_relevant INTEGER NOT NULL DEFAULT 0
                                        CHECK(constraint_relevant IN (0, 1)),
                evidence_hash       TEXT    COLLATE BINARY,
                observed_at         TEXT    COLLATE BINARY,
                created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_obs_edge
                ON observations (edge_id COLLATE BINARY)
            """,

            # --- edge_updates (audit trail, spec §7.8) ---
            """
            CREATE TABLE IF NOT EXISTS edge_updates (
                update_id           INTEGER PRIMARY KEY AUTOINCREMENT,
                edge_id             TEXT    NOT NULL COLLATE BINARY
                                        REFERENCES edges(edge_id),
                observation_id      INTEGER NOT NULL
                                        REFERENCES observations(observation_id),
                alpha_before        INTEGER NOT NULL,
                beta_before         INTEGER NOT NULL,
                alpha_after         INTEGER NOT NULL,
                beta_after          INTEGER NOT NULL,
                status_before       TEXT    NOT NULL COLLATE BINARY,
                status_after        TEXT    NOT NULL COLLATE BINARY,
                frozen_before       INTEGER NOT NULL,
                frozen_after        INTEGER NOT NULL,
                flags_json_before   TEXT    NOT NULL,
                flags_json_after    TEXT    NOT NULL,
                polarity            TEXT    NOT NULL COLLATE BINARY
                                        CHECK(polarity IN (
                                            'SUPPORT','AGAINST','NEUTRAL'
                                        )),
                increment           INTEGER NOT NULL DEFAULT 0,
                created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_edge_updates_edge
                ON edge_updates (edge_id COLLATE BINARY)
            """,

            # --- run_warnings ---
            """
            CREATE TABLE IF NOT EXISTS run_warnings (
                warning_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                code            TEXT    NOT NULL COLLATE BINARY,
                severity        TEXT    NOT NULL DEFAULT 'WARN'
                                    COLLATE BINARY
                                    CHECK(severity IN ('INFO','WARN','ERROR')),
                message         TEXT    NOT NULL DEFAULT '',
                context_json    TEXT    NOT NULL DEFAULT '{}',
                created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """,

            # --- derived_topk (populated by path search) ---
            """
            CREATE TABLE IF NOT EXISTS derived_topk (
                objective_id        TEXT    NOT NULL COLLATE BINARY
                                        REFERENCES objectives(objective_id),
                rank                INTEGER NOT NULL,
                edge_id_sequence    TEXT    NOT NULL,
                p_best_q8           INTEGER NOT NULL,
                p_worst_q8          INTEGER NOT NULL,
                confidence_band     TEXT    NOT NULL COLLATE BINARY,
                path_length         INTEGER NOT NULL,
                flags_json          TEXT    NOT NULL
                                        DEFAULT '{"conflict":false,"counterfactual_override":false,"prior_only":false,"stale":false}',
                created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (objective_id, rank)
            )
            """,
        ],
    ),
    (
        2,
        "Store immutable replay base state",
        [
            """
            ALTER TABLE edges ADD COLUMN base_alpha_i INTEGER NOT NULL DEFAULT 1
            """,
            """
            ALTER TABLE edges ADD COLUMN base_beta_i INTEGER NOT NULL DEFAULT 1
            """,
            """
            ALTER TABLE edges ADD COLUMN base_status TEXT NOT NULL DEFAULT 'HYPOTHESIZED' COLLATE BINARY
            """,
            """
            ALTER TABLE edges ADD COLUMN base_frozen INTEGER NOT NULL DEFAULT 0
            """,
            """
            ALTER TABLE edges ADD COLUMN base_flags_json TEXT NOT NULL
                DEFAULT '{"conflict":false,"counterfactual_override":false,"prior_only":false,"stale":false}'
            """,
            """
            UPDATE edges
               SET base_alpha_i = alpha_i,
                   base_beta_i = beta_i,
                   base_status = status,
                   base_frozen = frozen,
                   base_flags_json = flags_json
            """,
            """
            ALTER TABLE templates ADD COLUMN base_alpha_agg_i INTEGER NOT NULL DEFAULT 1
            """,
            """
            ALTER TABLE templates ADD COLUMN base_beta_agg_i INTEGER NOT NULL DEFAULT 1
            """,
            """
            ALTER TABLE templates ADD COLUMN base_sample_count INTEGER NOT NULL DEFAULT 0
            """,
            """
            UPDATE templates
               SET base_alpha_agg_i = alpha_agg_i,
                   base_beta_agg_i = beta_agg_i,
                   base_sample_count = sample_count
            """,
        ],
    ),
]


def get_current_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version, or 0 if no migrations applied."""
    try:
        cur = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        )
        row = cur.fetchone()
        return row[0] if row[0] is not None else 0
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return 0


def run_migrations(conn: sqlite3.Connection) -> int:
    """Apply all pending migrations idempotently.

    Returns:
        The schema version after migration.
    """
    current = get_current_version(conn)

    for version, description, statements in _MIGRATIONS:
        if version <= current:
            continue

        for sql in statements:
            conn.execute(sql)

        conn.execute(
            "INSERT INTO schema_version (version, description) VALUES (?, ?)",
            (version, description),
        )

    conn.commit()
    return get_current_version(conn)
