"""Probe execution framework: SAFE mode + call logging.

This is scaffolding for future live probe execution. No AWS SDK,
no live calls, no credentials required. Three executor modes:

    DRY_RUN:  Log what WOULD be called. No side effects. Default.
    CONFIRM:  Log + prompt for human confirmation before each call.
    LIVE:     Actually execute (future — not implemented yet).

Call log captures every probe attempt regardless of mode:
    - What was requested (edge, action, target)
    - What mode was active
    - Whether it was approved/skipped/executed
    - Result (if executed)
    - Timestamp

The planner feeds recommendations into the executor. The executor
decides whether to actually probe based on the mode.

Usage:
    executor = ProbeExecutor(conn, mode="DRY_RUN")
    results = executor.execute_plan(plan_result)
    # → logs all recommendations, executes none
    # → call_log table populated for audit

Future integration points:
    - LIVE mode: implement _execute_probe() with boto3/CloudTrail
    - CONFIRM mode: hook into CLI for interactive approval
    - Adapter: CloudTrail → observation ingestion pipeline
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Protocol


# ===================================================================
# Call log schema
# ===================================================================


CALL_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS call_log (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    edge_id         TEXT    NOT NULL COLLATE BINARY,
    action          TEXT    NOT NULL COLLATE BINARY,
    target_arn      TEXT    COLLATE BINARY,
    source_arn      TEXT    COLLATE BINARY,
    mode            TEXT    NOT NULL COLLATE BINARY
                        CHECK(mode IN ('DRY_RUN', 'CONFIRM', 'LIVE')),
    disposition     TEXT    NOT NULL COLLATE BINARY
                        CHECK(disposition IN (
                            'LOGGED', 'APPROVED', 'SKIPPED', 'EXECUTED', 'FAILED'
                        )),
    eig_score       REAL,
    reasons_json    TEXT,
    result          TEXT    COLLATE BINARY,
    error_message   TEXT    COLLATE BINARY,
    requested_at    TEXT    NOT NULL,
    completed_at    TEXT,
    run_hash        TEXT    COLLATE BINARY
)
"""

CALL_LOG_INDEX = """
CREATE INDEX IF NOT EXISTS idx_call_log_edge
    ON call_log (edge_id COLLATE BINARY)
"""


def ensure_call_log_table(conn: sqlite3.Connection) -> None:
    """Create the call_log table if it doesn't exist."""
    conn.execute(CALL_LOG_SCHEMA)
    conn.execute(CALL_LOG_INDEX)
    conn.commit()


# ===================================================================
# Probe result
# ===================================================================


class ProbeResult:
    """Result of a probe attempt."""

    __slots__ = ("edge_id", "disposition", "result", "error_message", "log_id")

    def __init__(
        self,
        edge_id: str,
        disposition: str,
        result: str | None = None,
        error_message: str | None = None,
        log_id: int | None = None,
    ) -> None:
        self.edge_id = edge_id
        self.disposition = disposition
        self.result = result
        self.error_message = error_message
        self.log_id = log_id

    def to_dict(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "disposition": self.disposition,
            "result": self.result,
            "error_message": self.error_message,
            "log_id": self.log_id,
        }


# ===================================================================
# Executor
# ===================================================================


class ProbeExecutor:
    """Execute probe recommendations with safety controls.

    Args:
        conn: Database connection (for call logging).
        mode: Execution mode ("DRY_RUN", "CONFIRM", "LIVE").
        confirm_fn: Callback for CONFIRM mode. Receives (edge_id, action,
            target_arn, eig) and returns True to approve.
    """

    VALID_MODES = ("DRY_RUN", "CONFIRM", "LIVE")

    def __init__(
        self,
        conn: sqlite3.Connection,
        mode: str = "DRY_RUN",
        confirm_fn: Any = None,
        run_hash: str | None = None,
    ) -> None:
        if mode not in self.VALID_MODES:
            raise ValueError(f"Invalid mode: {mode!r}. Must be one of {self.VALID_MODES}")
        self.conn = conn
        self.mode = mode
        self.confirm_fn = confirm_fn or (lambda *a: False)
        self.run_hash = run_hash
        ensure_call_log_table(conn)

    def execute_plan(self, plan_result: dict) -> list[ProbeResult]:
        """Execute all recommendations from a planner result.

        Args:
            plan_result: Output of plan_probes().

        Returns:
            List of ProbeResult for each candidate.
        """
        results = []
        for candidate in plan_result.get("candidates", []):
            result = self.execute_probe(candidate)
            results.append(result)
        return results

    def execute_probe(self, candidate: dict) -> ProbeResult:
        """Execute a single probe recommendation.

        Args:
            candidate: A candidate dict from plan_probes().candidates.

        Returns:
            ProbeResult with disposition based on mode.
        """
        edge_id = candidate["edge_id"]
        eig = candidate.get("eig", 0.0)
        reasons = candidate.get("reasons", [])

        # Resolve edge details
        row = self.conn.execute("""
            SELECT e.edge_type, n1.provider_id as src_arn, n2.provider_id as dst_arn
            FROM edges e
            JOIN nodes n1 ON n1.node_id = e.src_node_id
            JOIN nodes n2 ON n2.node_id = e.dst_node_id
            WHERE e.edge_id = ?
        """, (edge_id,)).fetchone()

        action = row["edge_type"] if row else "unknown"
        src_arn = row["src_arn"] if row else None
        dst_arn = row["dst_arn"] if row else None
        now = datetime.now(timezone.utc).isoformat()

        if self.mode == "DRY_RUN":
            disposition = "LOGGED"
            result_val = None
            error = None

        elif self.mode == "CONFIRM":
            approved = self.confirm_fn(edge_id, action, dst_arn, eig)
            if approved:
                disposition = "APPROVED"
                # In future: actually execute here
                result_val = None
                error = "CONFIRM mode: approved but execution not yet implemented"
            else:
                disposition = "SKIPPED"
                result_val = None
                error = None

        elif self.mode == "LIVE":
            disposition = "FAILED"
            result_val = None
            error = "LIVE mode not yet implemented"

        else:
            disposition = "FAILED"
            result_val = None
            error = f"Unknown mode: {self.mode}"

        # Log to call_log table
        cursor = self.conn.execute(
            """INSERT INTO call_log
               (edge_id, action, target_arn, source_arn, mode, disposition,
                eig_score, reasons_json, result, error_message,
                requested_at, completed_at, run_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                edge_id, action, dst_arn, src_arn,
                self.mode, disposition,
                eig, json.dumps(reasons),
                result_val, error,
                now, datetime.now(timezone.utc).isoformat(),
                self.run_hash,
            ),
        )
        self.conn.commit()
        log_id = cursor.lastrowid

        return ProbeResult(
            edge_id=edge_id,
            disposition=disposition,
            result=result_val,
            error_message=error,
            log_id=log_id,
        )

    def get_call_log(self) -> list[dict]:
        """Retrieve all call log entries."""
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM call_log ORDER BY log_id"
        ).fetchall()]

    def get_call_log_summary(self) -> dict:
        """Summarize call log by disposition."""
        rows = self.conn.execute(
            "SELECT disposition, COUNT(*) as cnt FROM call_log GROUP BY disposition"
        ).fetchall()
        return {r["disposition"]: r["cnt"] for r in rows}
