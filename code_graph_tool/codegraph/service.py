"""Use cases of the code graph. The CLI and the HTTP API are thin adapters over this class."""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional

from . import analytics
from .db import now_iso, transaction
from .domain import (C4_RANK, NODE_FIELDS, AdrStatus, EdgeKind, EvalCategory, Layer, NodeType, PolicyViolation,
                     Status, TaskKind, TaskStatus, ValidationError, Verdict, parse_enum)
from .loc import count_loc
from .repository import Repository
from .rules import DEFAULT_POLICIES, ChangeContext, Policy, validate_edge

_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
PROTECTED_META = {"rev", "schema_version", "design_locked"}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _csv(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [str(v).strip() for v in value if str(v).strip()]


class GraphService:
    def __init__(self, conn: sqlite3.Connection, policies: Optional[list[Policy]] = None,
                 project_root: Optional[Path] = None):
        self.conn = conn
        self.repo = Repository(conn)
        self.policies = DEFAULT_POLICIES if policies is None else policies
        self.project_root = project_root
        self._depth = 0

    # ---- plumbing -----------------------------------------------------------
    @contextmanager
    def _tx(self):
        """Re-entrant transaction so composite use cases (import) stay atomic."""
        if self._depth:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return
        self._depth = 1
        try:
            with transaction(self.conn):
                yield
        finally:
            self._depth = 0

    def _enforce(self, ctx: ChangeContext) -> None:
        for p in self.policies:
            p.check(ctx, self.repo)

    def _audit(self, actor, task_id, op, target, detail=None):
        self.repo.audit(actor=actor, task_id=task_id, op=op, target=target, detail=detail)

    def _require_approver(self, actor: Optional[str], what: str) -> None:
        approvers = _csv(self.repo.get_meta("approvers"))
        if actor not in approvers:
            raise PolicyViolation("APPROVER", f"{what} is reserved for approvers {approvers} (actor={actor!r})",
                                  {"next_step": "Escalate to the orchestrator."})

    # ---- project ------------------------------------------------------------
    def init_project(self, name: str, actor: Optional[str] = None) -> dict:
        with self._tx():
            self.repo.set_meta("project", name)
            self._audit(actor, None, "project.init", name)
        return self.config()

    def config(self) -> dict:
        meta = self.repo.all_meta()
        return {**{k: str(v) for k, v in analytics.DEFAULT_THRESHOLDS.items()}, **meta}

    def set_config(self, key: str, value: str, actor: Optional[str] = None) -> dict:
        if key in PROTECTED_META:
            raise ValidationError(f"'{key}' cannot be set directly")
        self._require_approver(actor, "config change")
        with self._tx():
            self.repo.set_meta(key, value)
            self._audit(actor, None, "config.set", key, {"value": value})
        return self.config()

    def set_design_lock(self, locked: bool, actor: Optional[str] = None) -> dict:
        self._require_approver(actor, "design lock/unlock")
        with self._tx():
            self.repo.set_meta("design_locked", "1" if locked else "0")
            self._audit(actor, None, "design.lock" if locked else "design.unlock", "design")
        return {"design_locked": locked}

    def rev(self) -> int:
        return int(self.repo.get_meta("rev", "0"))

    # ---- nodes --------------------------------------------------------------
    def _clean_fields(self, data: dict) -> dict:
        out = {}
        for k in NODE_FIELDS:
            if k not in data or data[k] is None:
                continue
            v = data[k]
            if k == "type":
                v = parse_enum(NodeType, v, "type").value
            elif k == "layer":
                v = parse_enum(Layer, v, "layer").value
            elif k == "status":
                v = parse_enum(Status, v, "status").value
            elif k == "complexity":
                v = int(v)
                if not 1 <= v <= 10:
                    raise ValidationError("complexity is a 1-10 self-assessment")
            elif k == "loc":
                v = int(v)
                if v < 0:
                    raise ValidationError("loc must be >= 0")
            elif k == "name":
                v = str(v).strip()
                if not v:
                    raise ValidationError("name must not be empty")
            out[k] = v
        return out

    def add_node(self, data: dict, *, actor=None, task_id=None, adr_id=None) -> dict:
        fields = self._clean_fields(data)
        if "name" not in fields or "type" not in fields:
            raise ValidationError("node needs at least name and type")
        node_id = str(data.get("id") or slug(fields["name"]))
        if not _ID_RE.match(node_id):
            raise ValidationError(f"invalid node id '{node_id}' (use letters, digits, _ . -)")
        with self._tx():
            if self.repo.find_node(node_id) or self.repo.find_node(fields["name"]):
                raise ValidationError(f"node id/name already exists: '{node_id}' / '{fields['name']}'")
            parent = self.repo.node(data["parent"]) if data.get("parent") else None
            fields.setdefault("layer", parent["layer"] if parent else None)
            if not fields["layer"]:
                raise ValidationError("node needs a layer (PLATFORM|USECASE) or a parent to inherit it from")
            fields.setdefault("status", Status.PLANNED.value)
            self._enforce(ChangeContext("node.create", actor, task_id, adr_id, fields={"id": node_id, **fields}))
            self.repo.insert_node(node_id, fields)
            node = self.repo.node(node_id)
            if parent:
                validate_edge(self.repo, EdgeKind.HAS, parent, node, "", None)
                self.repo.insert_edge({"kind": EdgeKind.HAS.value, "from_id": parent["id"], "to_id": node_id,
                                       "task_id": task_id, "created_by": actor})
            if adr_id:
                self.repo.link_adr(adr_id, node_id)
            if task_id:
                self.repo.add_task_node(task_id, node_id)
            self._audit(actor, task_id, "node.create", node_id, {**fields, "parent": parent and parent["id"]})
        return self.get_node(node_id)

    def update_node(self, ref: str, data: dict, *, actor=None, task_id=None, adr_id=None) -> dict:
        data = dict(data)
        status = data.pop("status", None)
        fields = self._clean_fields(data)
        with self._tx():
            node = self.repo.node(ref)
            changed = {k: v for k, v in fields.items() if node.get(k) != v}
            if "name" in changed:
                clash = self.repo.find_node(changed["name"])
                if clash and clash["id"] != node["id"]:
                    raise ValidationError(f"name '{changed['name']}' is already used by '{clash['id']}'")
            if changed:
                self._enforce(ChangeContext("node.update", actor, task_id, adr_id, node=node, fields=changed))
                self.repo.update_node(node["id"], changed)
                self._audit(actor, task_id, "node.update", node["id"],
                            {"before": {k: node.get(k) for k in changed}, "after": changed})
            if status is not None:
                self.set_status(node["id"], status, actor=actor, task_id=task_id, adr_id=adr_id)
        return self.get_node(node["id"])

    def set_status(self, ref: str, status: str, *, actor=None, task_id=None, adr_id=None) -> dict:
        new = parse_enum(Status, status, "status").value
        with self._tx():
            node = self.repo.node(ref)
            if node["status"] != new:
                self._enforce(ChangeContext("node.status", actor, task_id, adr_id, node=node, fields={"status": new}))
                self.repo.update_node(node["id"], {"status": new})
                self._audit(actor, task_id, "node.status", node["id"], {"from": node["status"], "to": new})
        return self.get_node(node["id"])

    def delete_node(self, ref: str, *, actor=None, task_id=None, adr_id=None) -> dict:
        with self._tx():
            node = self.repo.node(ref)
            if self.repo.children_of(node["id"]):
                raise ValidationError(f"'{node['id']}' has children; move or delete them first")
            self._enforce(ChangeContext("node.delete", actor, task_id, adr_id, node=node))
            self.repo.delete_node(node["id"])
            self._audit(actor, task_id, "node.delete", node["id"], node)
        return {"deleted": node["id"]}

    def get_node(self, ref: str) -> dict:
        r = self.repo
        n = r.node(ref)
        nid = n["id"]
        by_kind = lambda kind, **kw: r.edges(kind=kind.value, **kw)  # noqa: E731
        calls_out, calls_in = by_kind(EdgeKind.CALLS, from_id=nid), by_kind(EdgeKind.CALLS, to_id=nid)
        parent = r.parent_of(nid)
        return {
            **n,
            "parent": parent and parent["id"], "component": r.component_of(nid),
            "fan_out": len(calls_out), "fan_in": len(calls_in),
            "children": [{"id": c["id"], "name": c["name"], "type": c["type"], "status": c["status"]}
                         for c in r.children_of(nid)],
            "calls_out": calls_out, "calls_in": calls_in,
            "depends_out": by_kind(EdgeKind.DEPENDS, from_id=nid), "depends_in": by_kind(EdgeKind.DEPENDS, to_id=nid),
            "implements": by_kind(EdgeKind.IMPLEMENTS, from_id=nid),
            "implemented_by": by_kind(EdgeKind.IMPLEMENTS, to_id=nid),
            "tasks": r.list_tasks(node_id=nid), "adrs": r.list_adrs(node_id=nid),
            "eval_results": r.eval_results(node_id=nid), "latest_verdicts": r.latest_verdicts(nid),
            "utilities": [u for u in r.find_utilities([]) if u["node_id"] == nid],
            "history": r.list_audit(target=nid, limit=30),
        }

    def list_nodes(self, *, type=None, layer=None, status=None, q=None, parent=None) -> list[dict]:
        fan = self.repo.fan_counts()
        type = parse_enum(NodeType, type, "type").value if type else None
        layer = parse_enum(Layer, layer, "layer").value if layer else None
        status = parse_enum(Status, status, "status").value if status else None
        allowed = None
        if parent:
            allowed = set(self.repo.descendants(self.repo.node(parent)["id"]))
        out = []
        for n in self.repo.list_nodes(type=type, layer=layer, status=status, q=q):
            if allowed is not None and n["id"] not in allowed:
                continue
            out.append({"id": n["id"], "name": n["name"], "type": n["type"], "layer": n["layer"],
                        "status": n["status"], "code_path": n["code_path"], "change_count": n["change_count"],
                        **fan.get(n["id"], {"fan_in": 0, "fan_out": 0})})
        return out

    # ---- edges --------------------------------------------------------------
    def upsert_edge(self, kind: str, from_ref: str, to_ref: str, *, function_name: str = "",
                    signature: Optional[str] = None, purpose: Optional[str] = None,
                    actor=None, task_id=None, adr_id=None) -> dict:
        k = parse_enum(EdgeKind, kind, "edge kind")
        fn = (function_name or "").strip() if k is EdgeKind.CALLS else ""
        with self._tx():
            src, dst = self.repo.node(from_ref), self.repo.node(to_ref)
            existing = self.repo.find_edge(k.value, src["id"], dst["id"], fn)
            if existing and signature is None:
                signature = existing["signature"]
            validate_edge(self.repo, k, src, dst, fn, signature)
            edge = {"kind": k.value, "from_id": src["id"], "to_id": dst["id"], "function_name": fn,
                    "signature": signature, "purpose": purpose, "task_id": task_id, "created_by": actor}
            if existing and existing["signature"] == signature and (purpose is None or existing["purpose"] == purpose):
                return {"edge": existing, "created": False, "changed": False}
            self._enforce(ChangeContext("edge.upsert", actor, task_id, adr_id, node=src, target=dst,
                                        edge=edge, existing_edge=existing))
            if existing:
                upd = {"signature": signature}
                if purpose is not None:
                    upd["purpose"] = purpose
                self.repo.update_edge(existing["id"], upd)
                edge_id = existing["id"]
                self._audit(actor, task_id, "edge.update", f"{src['id']}->{dst['id']}",
                            {"kind": k.value, "function": fn, "before": existing["signature"], "after": signature})
            else:
                edge_id = self.repo.insert_edge(edge)
                self._audit(actor, task_id, "edge.create", f"{src['id']}->{dst['id']}",
                            {"kind": k.value, "function": fn, "signature": signature})
            saved = self.repo.edge_by_id(edge_id)
        return {"edge": saved, "created": existing is None, "changed": True,
                "contract_changed": bool(existing and existing["signature"] != signature)}

    def delete_edge(self, kind: str, from_ref: str, to_ref: str, *, function_name: str = "",
                    actor=None, task_id=None, adr_id=None) -> dict:
        k = parse_enum(EdgeKind, kind, "edge kind")
        with self._tx():
            src, dst = self.repo.node(from_ref), self.repo.node(to_ref)
            existing = self.repo.find_edge(k.value, src["id"], dst["id"], function_name if k is EdgeKind.CALLS else "")
            if not existing:
                raise ValidationError(f"no {k.value} edge {src['id']} -> {dst['id']} {function_name}".strip())
            self._enforce(ChangeContext("edge.delete", actor, task_id, adr_id, node=src, target=dst,
                                        edge=existing, existing_edge=existing))
            self.repo.delete_edge(existing["id"])
            self._audit(actor, task_id, "edge.delete", f"{src['id']}->{dst['id']}", existing)
        return {"deleted": existing}

    def list_edges(self, *, node=None, kind=None) -> list[dict]:
        kind = parse_enum(EdgeKind, kind, "edge kind").value if kind else None
        if node:
            nid = self.repo.node(node)["id"]
            return [e for e in self.repo.edges_of(nid) if kind is None or e["kind"] == kind]
        return self.repo.edges(kind=kind)

    # ---- tasks --------------------------------------------------------------
    def create_task(self, title: str, *, description=None, nodes=None, kind="FEATURE", agent=None,
                    adr_id=None, actor=None) -> dict:
        k = parse_enum(TaskKind, kind, "task kind").value
        with self._tx():
            node_ids = [self.repo.node(n)["id"] for n in _csv(nodes)]
            if not node_ids:
                raise ValidationError("a task must target at least one node (--nodes)")
            if adr_id:
                self.repo.adr(adr_id)
            task_id = self.repo.next_id("tasks", "T")
            self.repo.insert_task({"id": task_id, "title": title, "description": description, "kind": k,
                                   "status": TaskStatus.OPEN.value, "agent": agent, "adr_id": adr_id,
                                   "created_by": actor}, node_ids)
            self._audit(actor, task_id, "task.create", task_id, {"title": title, "nodes": node_ids})
        return self.repo.task(task_id)

    def start_task(self, task_id: str, *, agent=None, actor=None, adr_id=None) -> dict:
        with self._tx():
            t = self.repo.task(task_id)
            if t["status"] not in (TaskStatus.OPEN.value, TaskStatus.BLOCKED.value):
                raise ValidationError(f"task {task_id} is {t['status']}; only OPEN/BLOCKED tasks can start")
            adr = adr_id or t["adr_id"]
            for nid in t["nodes"]:
                self._enforce(ChangeContext("task.start", actor or agent, task_id, adr, node=self.repo.node(nid),
                                            task=t))
            upd = {"status": TaskStatus.IN_PROGRESS.value, "agent": agent or t["agent"] or actor}
            if not t["started_at"]:
                upd["started_at"] = now_iso()
            if adr and adr != t["adr_id"]:
                upd["adr_id"] = adr
            self.repo.update_task(task_id, upd)
            for nid in t["nodes"]:
                self._claim(task_id, nid, actor or agent)
            self._audit(actor or agent, task_id, "task.start", task_id, {"nodes": t["nodes"]})
        return self.repo.task(task_id)

    def _claim(self, task_id: str, node_id: str, actor) -> None:
        """Count the task against the node once and mark the node as being worked on."""
        if self.repo.mark_counted(task_id, node_id):
            self.repo.bump_change_count(node_id)
        node = self.repo.node(node_id)
        if node["status"] != Status.IN_PROGRESS.value:
            self.repo.update_node(node_id, {"status": Status.IN_PROGRESS.value})
            self._audit(actor, task_id, "node.status", node_id, {"from": node["status"], "to": "IN_PROGRESS"})

    def add_task_node(self, task_id: str, ref: str, *, actor=None, adr_id=None) -> dict:
        with self._tx():
            t = self.repo.task(task_id)
            node = self.repo.node(ref)
            if node["id"] in t["nodes"]:
                return t
            self._enforce(ChangeContext("task.add_node", actor, task_id, adr_id or t["adr_id"], node=node, task=t))
            self.repo.add_task_node(task_id, node["id"])
            if t["status"] == TaskStatus.IN_PROGRESS.value:
                self._claim(task_id, node["id"], actor)
            self._audit(actor, task_id, "task.add_node", task_id, {"node": node["id"]})
        return self.repo.task(task_id)

    def _close_task(self, task_id: str, status: TaskStatus, summary: Optional[str], actor) -> dict:
        with self._tx():
            t = self.repo.task(task_id)
            upd = {"status": status.value, "summary": summary}
            if status in (TaskStatus.DONE, TaskStatus.CANCELLED):
                upd["finished_at"] = now_iso()
            self.repo.update_task(task_id, upd)
            self._audit(actor, task_id, f"task.{status.value.lower()}", task_id, {"summary": summary})
        out = self.repo.task(task_id)
        if status is TaskStatus.DONE:
            open_nodes = [n for n in t["nodes"] if self.repo.node(n)["status"] in ("PLANNED", "IN_PROGRESS")]
            if open_nodes:
                out["warnings"] = [f"nodes still PLANNED/IN_PROGRESS: {open_nodes} (set COMPLETED/TESTED)"]
        return out

    def finish_task(self, task_id: str, summary: str, *, actor=None) -> dict:
        return self._close_task(task_id, TaskStatus.DONE, summary, actor)

    def block_task(self, task_id: str, reason: str, *, actor=None) -> dict:
        return self._close_task(task_id, TaskStatus.BLOCKED, reason, actor)

    def cancel_task(self, task_id: str, reason: str, *, actor=None) -> dict:
        return self._close_task(task_id, TaskStatus.CANCELLED, reason, actor)

    def get_task(self, task_id: str) -> dict:
        return self.repo.task(task_id)

    def list_tasks(self, *, status=None, agent=None, node=None) -> list[dict]:
        status = parse_enum(TaskStatus, status, "task status").value if status else None
        node_id = self.repo.node(node)["id"] if node else None
        return self.repo.list_tasks(status=status, agent=agent, node_id=node_id)

    # ---- ADRs ---------------------------------------------------------------
    def propose_adr(self, title: str, *, context=None, decision=None, consequences=None, nodes=None,
                    actor=None) -> dict:
        with self._tx():
            node_ids = [self.repo.node(n)["id"] for n in _csv(nodes)]
            adr_id = self.repo.next_id("adrs", "ADR")
            self.repo.insert_adr({"id": adr_id, "title": title, "status": AdrStatus.PROPOSED.value,
                                  "context": context, "decision": decision, "consequences": consequences,
                                  "author": actor}, node_ids)
            self._audit(actor, None, "adr.propose", adr_id, {"title": title, "nodes": node_ids})
        return self.repo.adr(adr_id)

    def decide_adr(self, adr_id: str, status: str, *, note=None, actor=None) -> dict:
        new = parse_enum(AdrStatus, status, "ADR status")
        self._require_approver(actor, "ADR decision")
        with self._tx():
            self.repo.adr(adr_id)
            self.repo.decide_adr(adr_id, new.value, actor, note)
            self._audit(actor, None, f"adr.{new.value.lower()}", adr_id, {"note": note})
        return self.repo.adr(adr_id)

    def link_adr(self, adr_id: str, nodes, *, actor=None) -> dict:
        self._require_approver(actor, "ADR linking")
        with self._tx():
            self.repo.adr(adr_id)
            for n in _csv(nodes):
                self.repo.link_adr(adr_id, self.repo.node(n)["id"])
            self._audit(actor, None, "adr.link", adr_id, {"nodes": _csv(nodes)})
        return self.repo.adr(adr_id)

    def get_adr(self, adr_id: str) -> dict:
        return self.repo.adr(adr_id)

    def list_adrs(self, *, status=None, node=None) -> list[dict]:
        status = parse_enum(AdrStatus, status, "ADR status").value if status else None
        return self.repo.list_adrs(status=status, node_id=self.repo.node(node)["id"] if node else None)

    # ---- utilities ----------------------------------------------------------
    def find_utilities(self, query: str) -> dict:
        words = [w for w in re.split(r"[\s_\-.]+", query or "") if len(w) > 1]
        matches = self.repo.find_utilities(words)
        seen = {m["name"] for m in matches}
        related = [u for u in self.repo.any_word_utilities(words) if u["name"] not in seen]
        return {"query": query, "matches": matches, "related": related[:15],
                "advice": "Reuse a match instead of writing a new utility." if matches else
                          "No exact match. Check 'related' before adding a new utility."}

    def add_utility(self, name: str, purpose: str, *, signature=None, module_path=None, node=None, actor=None) -> dict:
        if not purpose:
            raise ValidationError("utility needs a purpose")
        with self._tx():
            existing = self.repo.utility(name)
            if existing:
                raise ValidationError(f"utility '{name}' already exists - reuse it", {"existing": existing})
            node_id = self.repo.node(node)["id"] if node else None
            self.repo.insert_utility({"name": name, "purpose": purpose, "signature": signature,
                                      "module_path": module_path, "node_id": node_id, "created_by": actor})
            self._audit(actor, None, "utility.add", name, {"signature": signature, "module": module_path})
        return self.repo.utility(name)

    def list_utilities(self) -> list[dict]:
        return self.repo.find_utilities([])

    # ---- evals --------------------------------------------------------------
    def upsert_eval(self, data: dict, *, actor=None) -> dict:
        for key in ("id", "category", "title", "rule"):
            if not data.get(key):
                raise ValidationError(f"eval needs '{key}'")
        ev = {**data, "category": parse_enum(EvalCategory, data["category"], "eval category").value,
              "severity": str(data.get("severity") or "MAJOR").upper()}
        with self._tx():
            self.repo.upsert_eval(ev)
            self._audit(actor, None, "eval.upsert", ev["id"], {"title": ev["title"]})
        return self.repo.eval(ev["id"])

    def import_evals(self, evals: Iterable[dict], *, actor=None) -> dict:
        with self._tx():
            ids = [self.upsert_eval(e, actor=actor)["id"] for e in evals]
        return {"imported": len(ids), "ids": ids}

    def list_evals(self, *, category=None) -> list[dict]:
        cat = parse_enum(EvalCategory, category, "eval category").value if category else None
        return self.repo.list_evals(category=cat)

    def record_eval(self, eval_id: str, node_ref: str, verdict: str, *, notes=None, task_id=None, coder=None,
                    actor=None) -> dict:
        v = parse_enum(Verdict, verdict, "verdict").value
        if v == Verdict.FAIL.value and not notes:
            raise ValidationError("a FAIL verdict needs --notes with the finding and the expected fix")
        with self._tx():
            self.repo.eval(eval_id)
            node = self.repo.node(node_ref)
            if not coder and task_id:
                coder = self.repo.task(task_id)["agent"]
            if not coder:
                recent = [t for t in self.repo.list_tasks(node_id=node["id"]) if t["agent"]]
                coder = recent[-1]["agent"] if recent else node["owner"]
            rid = self.repo.insert_eval_result({"eval_id": eval_id, "node_id": node["id"], "task_id": task_id,
                                                "coder": coder, "reviewer": actor, "verdict": v, "notes": notes})
            self._audit(actor, task_id, "eval.record", node["id"], {"eval": eval_id, "verdict": v})
        return {"id": rid, "eval_id": eval_id, "node": node["id"], "verdict": v, "coder": coder,
                "latest_verdicts": self.repo.latest_verdicts(node["id"])}

    def eval_report(self, *, category=None) -> dict:
        cat = parse_enum(EvalCategory, category, "eval category").value if category else None
        return analytics.eval_report(self.repo, cat)

    # ---- analytics ----------------------------------------------------------
    def impact(self, ref: str, depth: int = 3) -> dict:
        return analytics.impact(self.repo, ref, depth)

    def metrics(self) -> dict:
        return analytics.metrics(self.repo)

    def check(self) -> dict:
        return analytics.check(self.repo)

    def scan_loc(self, *, actor=None, task_id=None, dry_run=False) -> dict:
        """Measure LOC from code_path. A measurement, not a design change, so policies do not apply.

        With a task, only that task's nodes are measured, so parallel agents never rewrite each other's nodes.
        """
        if self.project_root is None:
            raise ValidationError("project root unknown; set it with `cg config set project_root <path>`")
        changes, missing = [], []
        scope = set(self.repo.task(task_id)["nodes"]) if task_id else None
        with self._tx():
            for n in self.repo.list_nodes():
                if scope is not None and n["id"] not in scope:
                    continue
                if not n["code_path"]:
                    continue
                loc = count_loc(self.project_root, n["code_path"])
                if loc is None:
                    missing.append({"id": n["id"], "code_path": n["code_path"]})
                elif loc != n["loc"]:
                    if not dry_run:
                        self.repo.update_node(n["id"], {"loc": loc})
                    changes.append({"id": n["id"], "from": n["loc"], "to": loc})
            if not dry_run:
                self._audit(actor, task_id, "loc.scan", task_id or "project", {"changes": changes})
        return {"project_root": str(self.project_root), "dry_run": dry_run,
                "updated": changes, "path_not_found": missing}

    def audit(self, *, target=None, limit=100) -> list[dict]:
        return self.repo.list_audit(target=target, limit=limit)

    # ---- graph for UI -------------------------------------------------------
    def graph(self) -> dict:
        fan = self.repo.fan_counts()
        nodes = self.repo.list_nodes()
        parents = {e["to_id"]: e["from_id"] for e in self.repo.edges(kind=EdgeKind.HAS.value)}
        active = {}
        for t in self.repo.list_tasks(status=TaskStatus.IN_PROGRESS.value):
            for nid in t["nodes"]:
                active[nid] = {"task": t["id"], "agent": t["agent"]}
        out_nodes = [{**n, "parent": parents.get(n["id"]), "active": active.get(n["id"]),
                      **fan.get(n["id"], {"fan_in": 0, "fan_out": 0})} for n in nodes]
        edges = [e for e in self.repo.edges() if e["kind"] != EdgeKind.HAS.value]
        meta = self.repo.all_meta()
        return {"meta": {"project": meta.get("project"), "rev": int(meta.get("rev", 0)),
                         "design_locked": meta.get("design_locked") == "1"},
                "nodes": out_nodes, "edges": edges}

    # ---- seed import / export ---------------------------------------------
    def import_seed(self, doc: dict, *, actor=None, adr_id=None) -> dict:
        counts = {"nodes_created": 0, "nodes_updated": 0, "edges": 0, "utilities": 0, "evals": 0}
        nodes = sorted(doc.get("nodes", []), key=lambda n: C4_RANK[parse_enum(NodeType, n.get("type"), "type")])
        with self._tx():
            if doc.get("project") and not self.repo.get_meta("project"):
                self.repo.set_meta("project", doc["project"])
            for n in nodes:
                ref = n.get("id") or n.get("name")
                if ref and self.repo.find_node(ref):
                    self.update_node(ref, {k: v for k, v in n.items() if k in NODE_FIELDS},
                                     actor=actor, adr_id=adr_id)
                    if n.get("parent"):
                        self.upsert_edge("HAS", n["parent"], ref, actor=actor, adr_id=adr_id)
                    counts["nodes_updated"] += 1
                else:
                    self.add_node(n, actor=actor, adr_id=adr_id)
                    counts["nodes_created"] += 1
            for e in doc.get("edges", []):
                self.upsert_edge(e["kind"], e["from"], e["to"], function_name=e.get("function", ""),
                                 signature=e.get("signature"), purpose=e.get("purpose"), actor=actor, adr_id=adr_id)
                counts["edges"] += 1
            for u in doc.get("utilities", []):
                if not self.repo.utility(u["name"]):
                    self.add_utility(u["name"], u["purpose"], signature=u.get("signature"),
                                     module_path=u.get("module_path"), node=u.get("node"), actor=actor)
                    counts["utilities"] += 1
            if doc.get("evals"):
                counts["evals"] = self.import_evals(doc["evals"], actor=actor)["imported"]
        return counts

    def export_seed(self) -> dict:
        parents = {e["to_id"]: e["from_id"] for e in self.repo.edges(kind=EdgeKind.HAS.value)}
        nodes = []
        for n in self.repo.list_nodes():
            item = {"id": n["id"], **{k: n[k] for k in NODE_FIELDS if n.get(k) is not None}}
            if n["id"] in parents:
                item["parent"] = parents[n["id"]]
            nodes.append(item)
        edges = [{"kind": e["kind"], "from": e["from_id"], "to": e["to_id"],
                  **({"function": e["function_name"], "signature": e["signature"]} if e["function_name"] else {}),
                  **({"purpose": e["purpose"]} if e["purpose"] else {})}
                 for e in self.repo.edges() if e["kind"] != EdgeKind.HAS.value]
        utils = [{k: u[k] for k in ("name", "signature", "purpose", "module_path") if u.get(k)}
                 | ({"node": u["node_id"]} if u["node_id"] else {}) for u in self.list_utilities()]
        evals = [{k: e[k] for k in ("id", "category", "title", "rule", "check_method", "severity")}
                 for e in self.repo.list_evals()]
        return {"project": self.repo.get_meta("project"), "nodes": nodes, "edges": edges,
                "utilities": utils, "evals": evals}

