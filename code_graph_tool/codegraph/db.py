"""SQLite connection, schema and transaction helpers."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA_VERSION = "1"

DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS nodes (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    type            TEXT NOT NULL,
    layer           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'PLANNED',
    business_intent TEXT,
    extensibility   TEXT,
    contract        TEXT,
    code_path       TEXT,
    loc             INTEGER,
    complexity      INTEGER,
    complexity_note TEXT,
    owner           TEXT,
    change_count    INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT NOT NULL,
    from_id       TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    to_id         TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    function_name TEXT NOT NULL DEFAULT '',
    signature     TEXT,
    purpose       TEXT,
    task_id       TEXT,
    created_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (kind, from_id, to_id, function_name)
);
CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id, kind);
CREATE INDEX IF NOT EXISTS idx_edges_to   ON edges(to_id, kind);

CREATE TABLE IF NOT EXISTS adrs (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    status       TEXT NOT NULL,
    context      TEXT,
    decision     TEXT,
    consequences TEXT,
    author       TEXT,
    decided_by   TEXT,
    decision_note TEXT,
    created_at   TEXT NOT NULL,
    decided_at   TEXT
);
CREATE TABLE IF NOT EXISTS adr_nodes (
    adr_id  TEXT NOT NULL REFERENCES adrs(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    PRIMARY KEY (adr_id, node_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT,
    kind        TEXT NOT NULL DEFAULT 'FEATURE',
    status      TEXT NOT NULL DEFAULT 'OPEN',
    agent       TEXT,
    adr_id      TEXT REFERENCES adrs(id),
    summary     TEXT,
    created_by  TEXT,
    created_at  TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS task_nodes (
    task_id  TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    node_id  TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    counted  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (task_id, node_id)
);

CREATE TABLE IF NOT EXISTS utilities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    signature   TEXT,
    purpose     TEXT NOT NULL,
    module_path TEXT,
    node_id     TEXT REFERENCES nodes(id) ON DELETE SET NULL,
    created_by  TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evals (
    id           TEXT PRIMARY KEY,
    category     TEXT NOT NULL,
    title        TEXT NOT NULL,
    rule         TEXT NOT NULL,
    check_method TEXT,
    severity     TEXT NOT NULL DEFAULT 'MAJOR',
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eval_results (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    eval_id    TEXT NOT NULL REFERENCES evals(id) ON DELETE CASCADE,
    node_id    TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    task_id    TEXT,
    coder      TEXT,
    reviewer   TEXT,
    verdict    TEXT NOT NULL,
    notes      TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_results_node ON eval_results(node_id, eval_id);

CREATE TABLE IF NOT EXISTS audit (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    actor   TEXT,
    task_id TEXT,
    op      TEXT NOT NULL,
    target  TEXT,
    detail  TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_target ON audit(target);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=15, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")  # CLI agents + UI server write concurrently
    conn.executescript(DDL)
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('rev', '0')")
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('design_locked', '0')")
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('approvers', 'orchestrator,human')")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    """One write transaction; bumps the graph revision so the UI can live-refresh."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("UPDATE meta SET value = CAST(value AS INTEGER) + 1 WHERE key = 'rev'")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
