"""SQLite connection management and schema (CONTRACTS §4).

A single process-wide connection is reused (``check_same_thread=False`` so the
asyncio worker thread-pool may share it). WAL mode keeps reads non-blocking
during writes. Tests point ``DATA_DIR`` at a tmp dir and call
:func:`reset_connection` so a fresh database is created per test.
"""

from __future__ import annotations

import sqlite3

from app.storage import db_path

_connection: sqlite3.Connection | None = None

# DDL is idempotent (CREATE TABLE IF NOT EXISTS). Schema mirrors CONTRACTS §4
# exactly; the API/storage layer converts Row <-> pydantic models.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS topic(
  id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  background_path TEXT, settings_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS item(
  id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL REFERENCES topic(id) ON DELETE CASCADE,
  position INTEGER NOT NULL, slug TEXT NOT NULL, name TEXT NOT NULL,
  prompt TEXT NOT NULL DEFAULT '', seed INTEGER, sfx_path TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  UNIQUE(topic_id, position));
CREATE TABLE IF NOT EXISTS job(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, ref_id INTEGER,
  state TEXT NOT NULL DEFAULT 'queued', progress REAL NOT NULL DEFAULT 0,
  log TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
"""


def get_connection() -> sqlite3.Connection:
    """Return the process-wide SQLite connection (created on first use).

    The connection targets :func:`app.storage.db_path` and is configured with
    WAL journaling, foreign-key enforcement and ``sqlite3.Row`` rows.
    """

    global _connection
    if _connection is None:
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _connection = conn
    return _connection


def reset_connection() -> None:
    """Close and drop the cached connection (used between tests)."""

    global _connection
    if _connection is not None:
        try:
            _connection.close()
        finally:
            _connection = None


def init_db() -> None:
    """Create the schema if missing. Idempotent."""

    conn = get_connection()
    conn.executescript(_SCHEMA)
    conn.commit()
