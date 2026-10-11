"""`cg` command line: the agent-facing adapter over GraphService.

Output is JSON on stdout. Errors are JSON on stderr with exit codes:
  1 = unexpected, 2 = invalid input / not found, 3 = POLICY_VIOLATION (stop and escalate).
Identity: --actor/--task/--adr or env CG_ACTOR / CG_TASK / CG_ADR. Database: --db or env CG_DB.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import installer
from .db import connect
from .domain import GraphError
from .service import GraphService

TOOL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = TOOL_DIR / "code_graph.db"


def _common() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--db", default=argparse.SUPPRESS, help="sqlite path (env CG_DB)")
    p.add_argument("--actor", default=argparse.SUPPRESS, help="who is acting, e.g. coder-1 (env CG_ACTOR)")
    p.add_argument("--task", default=argparse.SUPPRESS, help="current task id (env CG_TASK)")
    p.add_argument("--adr", default=argparse.SUPPRESS, help="accepted ADR authorising the change (env CG_ADR)")
    p.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="indented JSON")
    return p


def build_parser() -> argparse.ArgumentParser:
    common = _common()
    root = argparse.ArgumentParser(prog="cg", parents=[common], description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = root.add_subparsers(dest="cmd", required=True)

    def cmd(parent, name, help_):
        return parent.add_parser(name, parents=[common], help=help_, description=help_)

    def group(name, help_):
        return cmd(sub, name, help_).add_subparsers(dest="sub", required=True)

    p = cmd(sub, "init", "initialise the graph for a project")
    p.add_argument("--project", required=True)
    p = cmd(sub, "install", "copy this tool into a project folder and initialise it")
    p.add_argument("project_dir")
    p.add_argument("--name", help="project name (default: folder name)")
    p.add_argument("--with-claude", action="store_true", help="also copy .claude skills/agents/playbooks")
    p.add_argument("--force", action="store_true", help="overwrite existing tool files (never the db)")
    p = cmd(sub, "serve", "run the HTTP API + UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8770)

    g = group("config", "project settings (thresholds, approvers, project_root)")
    cmd(g, "show", "show settings")
    p = cmd(g, "set", "set a setting (approver only)")
    p.add_argument("key")
    p.add_argument("value")

    g = group("design", "baseline the C4 design")
    for s in ("lock", "unlock", "status"):
        cmd(g, s, f"design {s}")

    p = cmd(sub, "import", "import a seed JSON (nodes, edges, utilities, evals)")
    p.add_argument("file")
    p = cmd(sub, "export", "export the graph as seed JSON")
    p.add_argument("file", nargs="?")

    g = group("node", "C4 nodes")
    p = cmd(g, "add", "add a node")
    p.add_argument("id")
    _node_fields(p, required=True)
    p.add_argument("--parent", help="containing node (creates the HAS edge)")
    p = cmd(g, "update", "update node fields")
    p.add_argument("ref")
    _node_fields(p, required=False)
    p.add_argument("--status")
    p = cmd(g, "status", "move a node through PLANNED/IN_PROGRESS/COMPLETED/TESTED/EVALUATED")
    p.add_argument("ref")
    p.add_argument("status")
    p = cmd(g, "get", "node detail with edges, tasks, ADRs, evals, history")
    p.add_argument("ref")
    p.add_argument("--brief", action="store_true", help="omit history and eval results")
    p = cmd(g, "list", "list nodes")
    for f in ("--type", "--layer", "--status", "--parent", "--q"):
        p.add_argument(f)
    p = cmd(g, "rm", "delete a node")
    p.add_argument("ref")

    g = group("edge", "HAS / DEPENDS / CALLS / IMPLEMENTS / USES edges")
    p = cmd(g, "add", "add or update an edge (CALLS needs --fn and --sig)")
    p.add_argument("kind")
    p.add_argument("from_ref")
    p.add_argument("to_ref")
    p.add_argument("--fn", default="")
    p.add_argument("--sig")
    p.add_argument("--purpose")
    p = cmd(g, "rm", "remove an edge")
    p.add_argument("kind")
    p.add_argument("from_ref")
    p.add_argument("to_ref")
    p.add_argument("--fn", default="")
    p = cmd(g, "list", "list edges")
    p.add_argument("--node")
    p.add_argument("--kind")

    g = group("task", "units of work; starting one counts a change on each node")
    p = cmd(g, "new", "create a task (orchestrator)")
    p.add_argument("--title", required=True)
    p.add_argument("--desc", help="business context + acceptance criteria")
    p.add_argument("--nodes", required=True, help="comma separated node ids")
    p.add_argument("--kind", default="FEATURE", help="FEATURE | REFINEMENT")
    p.add_argument("--agent")
    p = cmd(g, "start", "start/resume a task")
    p.add_argument("id")
    p.add_argument("--agent")
    p = cmd(g, "add-node", "add a node to a task")
    p.add_argument("id")
    p.add_argument("ref")
    for name, arg in (("done", "--summary"), ("block", "--reason"), ("cancel", "--reason")):
        p = cmd(g, name, f"{name} a task")
        p.add_argument("id")
        p.add_argument(arg, required=True, dest="text")
    p = cmd(g, "get", "task detail")
    p.add_argument("id")
    p = cmd(g, "list", "list tasks")
    p.add_argument("--status")
    p.add_argument("--agent")
    p.add_argument("--node")

    g = group("adr", "architecture decision records")
    p = cmd(g, "propose", "propose an ADR")
    p.add_argument("--title", required=True)
    p.add_argument("--context", required=True)
    p.add_argument("--decision", required=True)
    p.add_argument("--consequences")
    p.add_argument("--nodes", default="", help="comma separated node ids the ADR covers")
    for name in ("accept", "reject", "supersede"):
        p = cmd(g, name, f"{name} an ADR (approver only)")
        p.add_argument("id")
        p.add_argument("--note")
    p = cmd(g, "link", "link an ADR to more nodes (approver only)")
    p.add_argument("id")
    p.add_argument("nodes")
    p = cmd(g, "get", "ADR detail")
    p.add_argument("id")
    p = cmd(g, "list", "list ADRs")
    p.add_argument("--status")
    p.add_argument("--node")

    g = group("util", "shared utility registry - look up before writing a utility")
    p = cmd(g, "find", "search utilities by keywords")
    p.add_argument("words", nargs="+")
    p = cmd(g, "add", "register a new utility")
    p.add_argument("name")
    p.add_argument("--purpose", required=True)
    p.add_argument("--sig")
    p.add_argument("--module")
    p.add_argument("--node")
    cmd(g, "list", "list utilities")

    g = group("eval", "EVAL catalog and review results")
    p = cmd(g, "add", "add/update an eval")
    p.add_argument("id")
    p.add_argument("--category", required=True, help="ARCH|APP_DESIGN|CODE|BUSINESS|SECURITY|PERFORMANCE")
    p.add_argument("--title", required=True)
    p.add_argument("--rule", required=True)
    p.add_argument("--method", help="how to check: cg check rule, grep, test, manual review ...")
    p.add_argument("--severity", default="MAJOR")
    p = cmd(g, "import", "import evals from a JSON list")
    p.add_argument("file")
    p = cmd(g, "list", "list evals")
    p.add_argument("--category")
    p = cmd(g, "record", "record a review verdict for a node")
    p.add_argument("eval_id")
    p.add_argument("--node", required=True)
    p.add_argument("--verdict", required=True, help="PASS | FAIL | WAIVED")
    p.add_argument("--notes")
    p.add_argument("--coder", help="agent that wrote the code (default: task agent)")
    p = cmd(g, "report", "eval adherence: first-pass rate per eval and per coder")
    p.add_argument("--category")

    p = cmd(sub, "impact", "blast radius of changing a node")
    p.add_argument("ref")
    p.add_argument("--depth", type=int, default=3)
    cmd(sub, "metrics", "progress, component metrics, platform maturity")
    cmd(sub, "check", "deterministic architecture checks over the graph")
    p = cmd(sub, "scan-loc", "measure LOC from node code paths (scoped to --task when given)")
    p.add_argument("--dry-run", action="store_true", help="report differences without writing")
    p = cmd(sub, "audit", "change ledger")
    p.add_argument("--target")
    p.add_argument("--limit", type=int, default=50)
    return root


NODE_FLAGS = {"name": "--name", "type": "--type", "layer": "--layer", "business_intent": "--intent",
              "extensibility": "--ext", "contract": "--contract", "code_path": "--path", "loc": "--loc",
              "complexity": "--complexity", "complexity_note": "--complexity-note", "owner": "--owner"}


def _node_fields(p, required: bool):
    for field, flag in NODE_FLAGS.items():
        p.add_argument(flag, dest=field, required=required and field in ("name", "type"))


def _node_data(a) -> dict:
    return {f: getattr(a, f) for f in NODE_FLAGS if getattr(a, f, None) is not None}


def _read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _project_root(svc: GraphService, db_path: Path) -> Path:
    configured = svc.repo.get_meta("project_root")
    return (db_path.parent / configured).resolve() if configured else db_path.parent.parent.resolve()


def run(a, svc: GraphService, db_path: Path):  # noqa: C901 - flat dispatch table
    kw = {"actor": a.actor, "task_id": a.task, "adr_id": a.adr}
    c, s = a.cmd, getattr(a, "sub", None)
    if c == "init":
        return svc.init_project(a.project, actor=a.actor)
    if c == "config":
        return svc.config() if s == "show" else svc.set_config(a.key, a.value, actor=a.actor)
    if c == "design":
        return {"design_locked": svc.config()["design_locked"] == "1"} if s == "status" \
            else svc.set_design_lock(s == "lock", actor=a.actor)
    if c == "import":
        return svc.import_seed(_read_json(a.file), actor=a.actor, adr_id=a.adr)
    if c == "export":
        doc = svc.export_seed()
        if a.file:
            Path(a.file).write_text(json.dumps(doc, indent=2), encoding="utf-8")
            return {"exported": a.file, "nodes": len(doc["nodes"]), "edges": len(doc["edges"])}
        return doc
    if c == "node":
        if s == "add":
            return svc.add_node({"id": a.id, "parent": a.parent, **_node_data(a)}, **kw)
        if s == "update":
            data = _node_data(a)
            if a.status:
                data["status"] = a.status
            return svc.update_node(a.ref, data, **kw)
        if s == "status":
            return svc.set_status(a.ref, a.status, **kw)
        if s == "get":
            n = svc.get_node(a.ref)
            if a.brief:
                for k in ("history", "eval_results"):
                    n.pop(k, None)
            return n
        if s == "list":
            return svc.list_nodes(type=a.type, layer=a.layer, status=a.status, q=a.q, parent=a.parent)
        if s == "rm":
            return svc.delete_node(a.ref, **kw)
    if c == "edge":
        if s == "add":
            return svc.upsert_edge(a.kind, a.from_ref, a.to_ref, function_name=a.fn, signature=a.sig,
                                   purpose=a.purpose, **kw)
        if s == "rm":
            return svc.delete_edge(a.kind, a.from_ref, a.to_ref, function_name=a.fn, **kw)
        if s == "list":
            return svc.list_edges(node=a.node, kind=a.kind)
    if c == "task":
        if s == "new":
            return svc.create_task(a.title, description=a.desc, nodes=a.nodes, kind=a.kind, agent=a.agent,
                                   adr_id=a.adr, actor=a.actor)
        if s == "start":
            return svc.start_task(a.id, agent=a.agent or a.actor, actor=a.actor, adr_id=a.adr)
        if s == "add-node":
            return svc.add_task_node(a.id, a.ref, actor=a.actor, adr_id=a.adr)
        if s in ("done", "block", "cancel"):
            fn = {"done": svc.finish_task, "block": svc.block_task, "cancel": svc.cancel_task}[s]
            return fn(a.id, a.text, actor=a.actor)
        if s == "get":
            return svc.get_task(a.id)
        if s == "list":
            return svc.list_tasks(status=a.status, agent=a.agent, node=a.node)
    if c == "adr":
        if s == "propose":
            return svc.propose_adr(a.title, context=a.context, decision=a.decision, consequences=a.consequences,
                                   nodes=a.nodes, actor=a.actor)
        if s in ("accept", "reject", "supersede"):
            status = {"accept": "ACCEPTED", "reject": "REJECTED", "supersede": "SUPERSEDED"}[s]
            return svc.decide_adr(a.id, status, note=a.note, actor=a.actor)
        if s == "link":
            return svc.link_adr(a.id, a.nodes, actor=a.actor)
        if s == "get":
            return svc.get_adr(a.id)
        if s == "list":
            return svc.list_adrs(status=a.status, node=a.node)
    if c == "util":
        if s == "find":
            return svc.find_utilities(" ".join(a.words))
        if s == "add":
            return svc.add_utility(a.name, a.purpose, signature=a.sig, module_path=a.module, node=a.node,
                                   actor=a.actor)
        return svc.list_utilities()
    if c == "eval":
        if s == "add":
            return svc.upsert_eval({"id": a.id, "category": a.category, "title": a.title, "rule": a.rule,
                                    "check_method": a.method, "severity": a.severity}, actor=a.actor)
        if s == "import":
            data = _read_json(a.file)
            return svc.import_evals(data["evals"] if isinstance(data, dict) else data, actor=a.actor)
        if s == "list":
            return svc.list_evals(category=a.category)
        if s == "record":
            return svc.record_eval(a.eval_id, a.node, a.verdict, notes=a.notes, task_id=a.task, coder=a.coder,
                                   actor=a.actor)
        if s == "report":
            return svc.eval_report(category=a.category)
    if c == "impact":
        return svc.impact(a.ref, a.depth)
    if c == "metrics":
        return svc.metrics()
    if c == "check":
        return svc.check()
    if c == "scan-loc":
        return svc.scan_loc(actor=a.actor, task_id=a.task, dry_run=a.dry_run)
    if c == "audit":
        return svc.audit(target=a.target, limit=a.limit)
    raise GraphError(f"unknown command {c} {s or ''}")


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    for name, env in (("db", "CG_DB"), ("actor", "CG_ACTOR"), ("task", "CG_TASK"), ("adr", "CG_ADR")):
        if not hasattr(a, name):
            setattr(a, name, os.environ.get(env))
    a.pretty = getattr(a, "pretty", False)
    db_path = Path(a.db or DEFAULT_DB).resolve()
    indent = 2 if a.pretty else None
    try:
        if a.cmd == "install":
            out = installer.install(TOOL_DIR, Path(a.project_dir), name=a.name, with_claude=a.with_claude,
                                    force=a.force)
        elif a.cmd == "serve":
            return _serve(a, db_path)
        else:
            conn = connect(str(db_path))
            try:
                svc = GraphService(conn)
                svc.project_root = _project_root(svc, db_path)
                out = run(a, svc, db_path)
            finally:
                conn.close()
        print(json.dumps(out, indent=indent, default=str))
        return 0
    except GraphError as e:
        print(json.dumps(e.to_dict(), indent=indent, default=str), file=sys.stderr)
        return e.exit_code
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(json.dumps({"error": type(e).__name__, "message": str(e)}), file=sys.stderr)
        return 1


def _serve(a, db_path: Path) -> int:
    import uvicorn

    from .api import create_app
    conn = connect(str(db_path))
    root = _project_root(GraphService(conn), db_path)
    conn.close()
    app = create_app(str(db_path), project_root=root, ui_dir=TOOL_DIR / "ui")
    print(f"Code graph UI: http://{a.host}:{a.port}/ui/   API docs: http://{a.host}:{a.port}/docs   db: {db_path}")
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0
