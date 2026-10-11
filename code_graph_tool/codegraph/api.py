"""FastAPI adapter. Every route delegates to GraphService; no rules live here.

Headers: X-Actor (default 'human'), X-Task, X-ADR carry the same meaning as the CLI's --actor/--task/--adr.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import Body, Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .db import connect
from .domain import GraphError, NotFound, PolicyViolation
from .service import GraphService

STATUS_CODES = {NotFound: 404, PolicyViolation: 409}


class Ctx:
    def __init__(self, actor: str, task: Optional[str], adr: Optional[str]):
        self.kw = {"actor": actor, "task_id": task, "adr_id": adr}
        self.actor = actor


def create_app(db_path: str, project_root: Optional[Path] = None, ui_dir: Optional[Path] = None) -> FastAPI:
    app = FastAPI(title="Code Graph", version="1.0",
                  description="C4 code dependency graph: nodes, contracts (CALLS), tasks, ADRs, utilities, EVALs.")

    def svc():
        conn = connect(db_path)
        try:
            yield GraphService(conn, project_root=project_root)
        finally:
            conn.close()

    def ctx(x_actor: str = Header("human"), x_task: Optional[str] = Header(None),
            x_adr: Optional[str] = Header(None)) -> Ctx:
        return Ctx(x_actor, x_task, x_adr)

    @app.exception_handler(GraphError)
    async def _graph_error(_: Request, exc: GraphError):
        return JSONResponse(exc.to_dict(), status_code=STATUS_CODES.get(type(exc), 422))

    # ---- read ---------------------------------------------------------------
    @app.get("/api/graph")
    def graph(s: GraphService = Depends(svc)):
        return s.graph()

    @app.get("/api/rev")
    def rev(s: GraphService = Depends(svc)):
        return {"rev": s.rev()}

    @app.get("/api/config")
    def config(s: GraphService = Depends(svc)):
        return s.config()

    @app.get("/api/nodes")
    def nodes(type: Optional[str] = None, layer: Optional[str] = None, status: Optional[str] = None,
              q: Optional[str] = None, parent: Optional[str] = None, s: GraphService = Depends(svc)):
        return s.list_nodes(type=type, layer=layer, status=status, q=q, parent=parent)

    @app.get("/api/nodes/{ref}")
    def node(ref: str, s: GraphService = Depends(svc)):
        return s.get_node(ref)

    @app.get("/api/edges")
    def edges(node: Optional[str] = None, kind: Optional[str] = None, s: GraphService = Depends(svc)):
        return s.list_edges(node=node, kind=kind)

    @app.get("/api/impact/{ref}")
    def impact(ref: str, depth: int = Query(3, ge=1, le=10), s: GraphService = Depends(svc)):
        return s.impact(ref, depth)

    @app.get("/api/metrics")
    def metrics(s: GraphService = Depends(svc)):
        return s.metrics()

    @app.get("/api/check")
    def check(s: GraphService = Depends(svc)):
        return s.check()

    @app.get("/api/tasks")
    def tasks(status: Optional[str] = None, agent: Optional[str] = None, node: Optional[str] = None,
              s: GraphService = Depends(svc)):
        return s.list_tasks(status=status, agent=agent, node=node)

    @app.get("/api/tasks/{task_id}")
    def task(task_id: str, s: GraphService = Depends(svc)):
        return s.get_task(task_id)

    @app.get("/api/adrs")
    def adrs(status: Optional[str] = None, node: Optional[str] = None, s: GraphService = Depends(svc)):
        return s.list_adrs(status=status, node=node)

    @app.get("/api/adrs/{adr_id}")
    def adr(adr_id: str, s: GraphService = Depends(svc)):
        return s.get_adr(adr_id)

    @app.get("/api/utilities")
    def utilities(q: Optional[str] = None, s: GraphService = Depends(svc)):
        return s.find_utilities(q) if q else s.list_utilities()

    @app.get("/api/evals")
    def evals(category: Optional[str] = None, s: GraphService = Depends(svc)):
        return s.list_evals(category=category)

    @app.get("/api/evals/report")
    def eval_report(category: Optional[str] = None, s: GraphService = Depends(svc)):
        return s.eval_report(category=category)

    @app.get("/api/audit")
    def audit(target: Optional[str] = None, limit: int = 100, s: GraphService = Depends(svc)):
        return s.audit(target=target, limit=limit)

    @app.get("/api/export")
    def export(s: GraphService = Depends(svc)):
        return s.export_seed()

    # ---- write --------------------------------------------------------------
    @app.post("/api/nodes")
    def add_node(body: dict = Body(...), c: Ctx = Depends(ctx), s: GraphService = Depends(svc)):
        return s.add_node(body, **c.kw)

    @app.patch("/api/nodes/{ref}")
    def update_node(ref: str, body: dict = Body(...), c: Ctx = Depends(ctx), s: GraphService = Depends(svc)):
        return s.update_node(ref, body, **c.kw)

    @app.delete("/api/nodes/{ref}")
    def delete_node(ref: str, c: Ctx = Depends(ctx), s: GraphService = Depends(svc)):
        return s.delete_node(ref, **c.kw)

    @app.post("/api/edges")
    def add_edge(body: dict = Body(...), c: Ctx = Depends(ctx), s: GraphService = Depends(svc)):
        return s.upsert_edge(body["kind"], body["from"], body["to"], function_name=body.get("function", ""),
                             signature=body.get("signature"), purpose=body.get("purpose"), **c.kw)

    @app.post("/api/edges/delete")
    def delete_edge(body: dict = Body(...), c: Ctx = Depends(ctx), s: GraphService = Depends(svc)):
        return s.delete_edge(body["kind"], body["from"], body["to"], function_name=body.get("function", ""), **c.kw)

    @app.post("/api/tasks")
    def create_task(body: dict = Body(...), c: Ctx = Depends(ctx), s: GraphService = Depends(svc)):
        return s.create_task(body["title"], description=body.get("description"), nodes=body.get("nodes"),
                             kind=body.get("kind", "FEATURE"), agent=body.get("agent"),
                             adr_id=body.get("adr") or c.kw["adr_id"], actor=c.actor)

    @app.post("/api/tasks/{task_id}/{action}")
    def task_action(task_id: str, action: str, body: dict = Body(default={}), c: Ctx = Depends(ctx),
                    s: GraphService = Depends(svc)):
        if action == "start":
            return s.start_task(task_id, agent=body.get("agent"), actor=c.actor, adr_id=c.kw["adr_id"])
        if action in ("done", "block", "cancel"):
            fn = {"done": s.finish_task, "block": s.block_task, "cancel": s.cancel_task}[action]
            return fn(task_id, body.get("summary") or body.get("reason") or "", actor=c.actor)
        raise NotFound(f"unknown task action '{action}'")

    @app.post("/api/adrs")
    def propose_adr(body: dict = Body(...), c: Ctx = Depends(ctx), s: GraphService = Depends(svc)):
        return s.propose_adr(body["title"], context=body.get("context"), decision=body.get("decision"),
                             consequences=body.get("consequences"), nodes=body.get("nodes"), actor=c.actor)

    @app.post("/api/adrs/{adr_id}/decide")
    def decide_adr(adr_id: str, body: dict = Body(...), c: Ctx = Depends(ctx), s: GraphService = Depends(svc)):
        return s.decide_adr(adr_id, body["status"], note=body.get("note"), actor=c.actor)

    @app.post("/api/utilities")
    def add_utility(body: dict = Body(...), c: Ctx = Depends(ctx), s: GraphService = Depends(svc)):
        return s.add_utility(body["name"], body.get("purpose"), signature=body.get("signature"),
                             module_path=body.get("module_path"), node=body.get("node"), actor=c.actor)

    @app.post("/api/evals")
    def upsert_eval(body: dict = Body(...), c: Ctx = Depends(ctx), s: GraphService = Depends(svc)):
        return s.upsert_eval(body, actor=c.actor)

    @app.post("/api/evals/results")
    def record_eval(body: dict = Body(...), c: Ctx = Depends(ctx), s: GraphService = Depends(svc)):
        return s.record_eval(body["eval_id"], body["node"], body["verdict"], notes=body.get("notes"),
                             task_id=body.get("task") or c.kw["task_id"], coder=body.get("coder"), actor=c.actor)

    # ---- UI -----------------------------------------------------------------
    if ui_dir and ui_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")

        @app.get("/", include_in_schema=False)
        def root():
            return RedirectResponse("/ui/")

    return app
