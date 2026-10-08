"""SQLite store for ARF-RT (spec §6).

Provides:
  - connect(): Opens DB with hardened PRAGMAs (WAL, foreign_keys, busy_timeout)
  - backup(): SQLite backup API for consistent DB copies
  - transaction(): Context manager for explicit transactions
  - run_migrations on connect
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from arf_rt.config import SQLITE_BUSY_TIMEOUT_MS
from arf_rt.storage.migrations import run_migrations


def connect(
    db_path: str | Path,
    *,
    read_only: bool = False,
    run_migrations_on_connect: bool = True,
) -> sqlite3.Connection:
    """Open a SQLite connection with hardened PRAGMAs per spec §6.1.

    PRAGMAs applied:
      - journal_mode = WAL (concurrent reads)
      - foreign_keys = ON (referential integrity)
      - busy_timeout = SQLITE_BUSY_TIMEOUT_MS
      - synchronous = NORMAL (safe with WAL)

    Args:
        db_path: Path to the SQLite database file. Use ":memory:" for in-memory.
        read_only: If True, open in read-only mode (for baseline in what-if).
        run_migrations_on_connect: If True, run pending migrations.

    Returns:
        Configured sqlite3.Connection with Row factory.
    """
    db_str = str(db_path)

    if read_only and db_str != ":memory:":
        uri = f"file:{db_str}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(db_str)

    conn.row_factory = sqlite3.Row

    # Hardened PRAGMAs — spec §6.1
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")

    if run_migrations_on_connect and not read_only:
        run_migrations(conn)

    return conn


def backup(src_conn: sqlite3.Connection, dst_path: str | Path) -> None:
    """Create a consistent backup of src_conn to dst_path using SQLite backup API.

    This is used by what-if to fork the baseline DB (spec §17.1).

    Args:
        src_conn: Source database connection.
        dst_path: Path for the backup database file.
    """
    dst_path = Path(dst_path)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    dst_conn = sqlite3.connect(str(dst_path))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for an explicit transaction.

    Commits on success, rolls back on exception.

    Usage:
        with transaction(conn) as tx:
            tx.execute(...)
    """
    conn.execute("BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
