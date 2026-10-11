"""Data access for the code graph. Plain SQL, no governance rules.

Rules live in `rules.py`; use-case orchestration lives in `service.py`.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Iterable, Optional

from .db import now_iso
from .domain import ACTIVE_TASK_STATUSES, EdgeKind, NODE_FIELDS, NotFound


def _row(r: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(r) if r is not None else None


def _rows(rs: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rs]


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _q(self, sql: str, params: tuple = ()) -> list[dict]:
        return _rows(self.conn.execute(sql, params).fetchall())

    def _one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        return _row(self.conn.execute(sql, params).fetchone())

    # ---- meta ---------------------------------------------------------------
    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        r = self._one("SELECT value FROM meta WHERE key = ?", (key,))
        return r["value"] if r else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) "
                          "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def all_meta(self) -> dict:
        return {r["key"]: r["value"] for r in self._q("SELECT key, value FROM meta")}

    # ---- nodes --------------------------------------------------------------
    def find_node(self, ref: str) -> Optional[dict]:
        return (self._one("SELECT * FROM nodes WHERE id = ?", (ref,))
                or self._one("SELECT * FROM nodes WHERE name = ?", (ref,))
                or self._one("SELECT * FROM nodes WHERE lower(name) = lower(?)", (ref,)))

    def node(self, ref: str) -> dict:
        n = self.find_node(ref)
        if n is None:
            raise NotFound(f"node '{ref}' not found")
        return n

    def list_nodes(self, *, type=None, layer=None, status=None, q=None) -> list[dict]:
        sql, params = "SELECT * FROM nodes WHERE 1=1", []
        for col, val in (("type", type), ("layer", layer), ("status", status)):
            if val:
                sql += f" AND {col} = ?"
                params.append(val)
        for word in (q or "").split():
            sql += " AND (id LIKE ? OR name LIKE ? OR business_intent LIKE ? OR code_path LIKE ?)"
            params += [f"%{word}%"] * 4
        return self._q(sql + " ORDER BY id", tuple(params))

    def insert_node(self, node_id: str, fields: dict) -> None:
        ts = now_iso()
        cols = ["id", *fields.keys(), "created_at", "updated_at"]
        self.conn.execute(f"INSERT INTO nodes ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                          (node_id, *fields.values(), ts, ts))

    def update_node(self, node_id: str, fields: dict) -> None:
        fields = {k: v for k, v in fields.items() if k in NODE_FIELDS or k == "change_count"}
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE nodes SET {sets}, updated_at = ? WHERE id = ?",
                          (*fields.values(), now_iso(), node_id))

    def bump_change_count(self, node_id: str) -> None:
        self.conn.execute("UPDATE nodes SET change_count = change_count + 1, updated_at = ? WHERE id = ?",
                          (now_iso(), node_id))

    def delete_node(self, node_id: str) -> None:
        self.conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))

    # ---- edges --------------------------------------------------------------
    def find_edge(self, kind: str, from_id: str, to_id: str, function_name: str = "") -> Optional[dict]:
        return self._one("SELECT * FROM edges WHERE kind = ? AND from_id = ? AND to_id = ? AND function_name = ?",
                         (kind, from_id, to_id, function_name or ""))

    def edge_by_id(self, edge_id: int) -> Optional[dict]:
        return self._one("SELECT * FROM edges WHERE id = ?", (edge_id,))

    def edges(self, *, kind=None, from_id=None, to_id=None, function_name=None) -> list[dict]:
        sql, params = "SELECT * FROM edges WHERE 1=1", []
        for col, val in (("kind", kind), ("from_id", from_id), ("to_id", to_id), ("function_name", function_name)):
            if val is not None:
                sql += f" AND {col} = ?"
                params.append(val)
        return self._q(sql + " ORDER BY id", tuple(params))

    def edges_of(self, node_id: str) -> list[dict]:
        return self._q("SELECT * FROM edges WHERE from_id = ? OR to_id = ? ORDER BY kind, id", (node_id, node_id))

    def insert_edge(self, e: dict) -> int:
        ts = now_iso()
        cur = self.conn.execute(
            "INSERT INTO edges (kind, from_id, to_id, function_name, signature, purpose, task_id, created_by,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (e["kind"], e["from_id"], e["to_id"], e.get("function_name") or "", e.get("signature"),
             e.get("purpose"), e.get("task_id"), e.get("created_by"), ts, ts))
        return cur.lastrowid

    def update_edge(self, edge_id: int, fields: dict) -> None:
        allowed = {k: v for k, v in fields.items() if k in ("signature", "purpose", "task_id")}
        if allowed:
            sets = ", ".join(f"{k} = ?" for k in allowed)
            self.conn.execute(f"UPDATE edges SET {sets}, updated_at = ? WHERE id = ?",
                              (*allowed.values(), now_iso(), edge_id))

    def delete_edge(self, edge_id: int) -> None:
        self.conn.execute("DELETE FROM edges WHERE id = ?", (edge_id,))

    def parent_of(self, node_id: str) -> Optional[dict]:
        e = self._one("SELECT from_id FROM edges WHERE kind = 'HAS' AND to_id = ?", (node_id,))
        return self.find_node(e["from_id"]) if e else None

    def children_of(self, node_id: str) -> list[dict]:
        return self._q("SELECT n.* FROM nodes n JOIN edges e ON e.to_id = n.id "
                       "WHERE e.kind = 'HAS' AND e.from_id = ? ORDER BY n.id", (node_id,))

    def descendants(self, node_id: str) -> list[str]:
        out, stack = [], [node_id]
        while stack:
            for c in self.children_of(stack.pop()):
                out.append(c["id"])
                stack.append(c["id"])
        return out

    def component_of(self, node_id: str) -> Optional[str]:
        """Top-most ancestor via HAS (the C4 component boundary), or the node itself if it has no parent."""
        current, seen = node_id, set()
        while current not in seen:
            seen.add(current)
            p = self.parent_of(current)
            if p is None:
                return current
            current = p["id"]
        return current

    def fan_counts(self) -> dict[str, dict]:
        counts: dict[str, dict] = {}
        for r in self._q("SELECT from_id, to_id FROM edges WHERE kind = ?", (EdgeKind.CALLS.value,)):
            counts.setdefault(r["from_id"], {"fan_in": 0, "fan_out": 0})["fan_out"] += 1
            counts.setdefault(r["to_id"], {"fan_in": 0, "fan_out": 0})["fan_in"] += 1
        return counts

    # ---- ADRs ---------------------------------------------------------------
    def next_id(self, table: str, prefix: str) -> str:
        rows = self._q(f"SELECT id FROM {table} WHERE id LIKE ?", (f"{prefix}-%",))
        nums = [int(r["id"].split("-")[-1]) for r in rows if r["id"].split("-")[-1].isdigit()]
        return f"{prefix}-{(max(nums) + 1 if nums else 1):04d}"

    def insert_adr(self, adr: dict, node_ids: list[str]) -> None:
        self.conn.execute("INSERT INTO adrs (id, title, status, context, decision, consequences, author, created_at)"
                          " VALUES (?,?,?,?,?,?,?,?)",
                          (adr["id"], adr["title"], adr["status"], adr.get("context"), adr.get("decision"),
                           adr.get("consequences"), adr.get("author"), now_iso()))
        for nid in node_ids:
            self.link_adr(adr["id"], nid)

    def link_adr(self, adr_id: str, node_id: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO adr_nodes (adr_id, node_id) VALUES (?, ?)", (adr_id, node_id))

    def adr(self, adr_id: str) -> dict:
        a = self._one("SELECT * FROM adrs WHERE id = ?", (adr_id,))
        if a is None:
            raise NotFound(f"ADR '{adr_id}' not found")
        a["nodes"] = [r["node_id"] for r in self._q("SELECT node_id FROM adr_nodes WHERE adr_id = ?", (adr_id,))]
        return a

    def list_adrs(self, *, status=None, node_id=None) -> list[dict]:
        if node_id:
            return self._q("SELECT a.* FROM adrs a JOIN adr_nodes an ON an.adr_id = a.id "
                           "WHERE an.node_id = ? ORDER BY a.id", (node_id,))
        if status:
            return self._q("SELECT * FROM adrs WHERE status = ? ORDER BY id", (status,))
        return self._q("SELECT * FROM adrs ORDER BY id")

    def decide_adr(self, adr_id: str, status: str, actor: str, note: Optional[str]) -> None:
        self.conn.execute("UPDATE adrs SET status = ?, decided_by = ?, decision_note = ?, decided_at = ? WHERE id = ?",
                          (status, actor, note, now_iso(), adr_id))

    # ---- tasks --------------------------------------------------------------
    def insert_task(self, t: dict, node_ids: list[str]) -> None:
        self.conn.execute("INSERT INTO tasks (id, title, description, kind, status, agent, adr_id, created_by,"
                          " created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                          (t["id"], t["title"], t.get("description"), t["kind"], t["status"], t.get("agent"),
                           t.get("adr_id"), t.get("created_by"), now_iso()))
        for nid in node_ids:
            self.add_task_node(t["id"], nid)

    def add_task_node(self, task_id: str, node_id: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO task_nodes (task_id, node_id) VALUES (?, ?)", (task_id, node_id))

    def mark_counted(self, task_id: str, node_id: str) -> bool:
        """Count a task against a node exactly once. Returns True if this call counted it."""
        cur = self.conn.execute("UPDATE task_nodes SET counted = 1 WHERE task_id = ? AND node_id = ? AND counted = 0",
                                (task_id, node_id))
        return cur.rowcount == 1

    def task(self, task_id: str) -> dict:
        t = self._one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if t is None:
            raise NotFound(f"task '{task_id}' not found")
        t["nodes"] = [r["node_id"] for r in self._q("SELECT node_id FROM task_nodes WHERE task_id = ?", (task_id,))]
        return t

    def update_task(self, task_id: str, fields: dict) -> None:
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?", (*fields.values(), task_id))

    def list_tasks(self, *, status=None, agent=None, node_id=None) -> list[dict]:
        sql, params = "SELECT DISTINCT t.* FROM tasks t LEFT JOIN task_nodes tn ON tn.task_id = t.id WHERE 1=1", []
        for col, val in (("t.status", status), ("t.agent", agent), ("tn.node_id", node_id)):
            if val:
                sql += f" AND {col} = ?"
                params.append(val)
        tasks = self._q(sql + " ORDER BY t.id", tuple(params))
        for t in tasks:
            t["nodes"] = [r["node_id"] for r in self._q("SELECT node_id FROM task_nodes WHERE task_id = ?", (t["id"],))]
        return tasks

    def active_tasks_for_node(self, node_id: str) -> list[dict]:
        marks = ",".join("?" * len(ACTIVE_TASK_STATUSES))
        return self._q(f"SELECT t.id, t.title, t.agent, t.status FROM tasks t JOIN task_nodes tn ON tn.task_id = t.id "
                       f"WHERE tn.node_id = ? AND t.status IN ({marks})",
                       (node_id, *[s.value for s in ACTIVE_TASK_STATUSES]))

    # ---- utilities ----------------------------------------------------------
    def find_utilities(self, words: list[str]) -> list[dict]:
        sql, params = "SELECT * FROM utilities WHERE 1=1", []
        for w in words:
            sql += " AND (name LIKE ? OR purpose LIKE ? OR signature LIKE ? OR module_path LIKE ?)"
            params += [f"%{w}%"] * 4
        return self._q(sql + " ORDER BY name", tuple(params))

    def any_word_utilities(self, words: list[str]) -> list[dict]:
        if not words:
            return []
        clause = " OR ".join(["name LIKE ? OR purpose LIKE ?"] * len(words))
        params = [p for w in words for p in (f"%{w}%", f"%{w}%")]
        return self._q(f"SELECT * FROM utilities WHERE {clause} ORDER BY name", tuple(params))

    def utility(self, name: str) -> Optional[dict]:
        return self._one("SELECT * FROM utilities WHERE lower(name) = lower(?)", (name,))

    def insert_utility(self, u: dict) -> None:
        self.conn.execute("INSERT INTO utilities (name, signature, purpose, module_path, node_id, created_by, created_at)"
                          " VALUES (?,?,?,?,?,?,?)",
                          (u["name"], u.get("signature"), u["purpose"], u.get("module_path"), u.get("node_id"),
                           u.get("created_by"), now_iso()))

    # ---- evals --------------------------------------------------------------
    def upsert_eval(self, ev: dict) -> None:
        self.conn.execute(
            "INSERT INTO evals (id, category, title, rule, check_method, severity, active, created_at)"
            " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET category = excluded.category,"
            " title = excluded.title, rule = excluded.rule, check_method = excluded.check_method,"
            " severity = excluded.severity, active = excluded.active",
            (ev["id"], ev["category"], ev["title"], ev["rule"], ev.get("check_method"), ev.get("severity", "MAJOR"),
             1 if ev.get("active", True) else 0, now_iso()))

    def eval(self, eval_id: str) -> dict:
        e = self._one("SELECT * FROM evals WHERE id = ?", (eval_id,))
        if e is None:
            raise NotFound(f"eval '{eval_id}' not found")
        return e

    def list_evals(self, *, category=None) -> list[dict]:
        if category:
            return self._q("SELECT * FROM evals WHERE category = ? ORDER BY id", (category,))
        return self._q("SELECT * FROM evals ORDER BY category, id")

    def insert_eval_result(self, r: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO eval_results (eval_id, node_id, task_id, coder, reviewer, verdict, notes, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (r["eval_id"], r["node_id"], r.get("task_id"), r.get("coder"), r.get("reviewer"), r["verdict"],
             r.get("notes"), now_iso()))
        return cur.lastrowid

    def eval_results(self, *, node_id=None, eval_id=None) -> list[dict]:
        sql, params = "SELECT * FROM eval_results WHERE 1=1", []
        for col, val in (("node_id", node_id), ("eval_id", eval_id)):
            if val:
                sql += f" AND {col} = ?"
                params.append(val)
        return self._q(sql + " ORDER BY id", tuple(params))

    def latest_verdicts(self, node_id: str) -> dict[str, str]:
        """eval_id -> most recent verdict for the node."""
        out: dict[str, str] = {}
        for r in self._q("SELECT eval_id, verdict FROM eval_results WHERE node_id = ? ORDER BY id", (node_id,)):
            out[r["eval_id"]] = r["verdict"]
        return out

    # ---- audit --------------------------------------------------------------
    def audit(self, *, actor, task_id, op, target, detail) -> None:
        self.conn.execute("INSERT INTO audit (ts, actor, task_id, op, target, detail) VALUES (?,?,?,?,?,?)",
                          (now_iso(), actor, task_id, op, target, json.dumps(detail, default=str) if detail else None))

    def list_audit(self, *, target=None, limit=100) -> list[dict]:
        if target:
            return self._q("SELECT * FROM audit WHERE target = ? OR target LIKE ? ORDER BY id DESC LIMIT ?",
                           (target, f"%{target}%", limit))
        return self._q("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
