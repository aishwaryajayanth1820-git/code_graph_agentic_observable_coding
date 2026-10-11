"""Read-only analysis: blast radius, component metrics, platform maturity, graph checks, eval adherence.

Everything here is deterministic so agents can call it instead of reasoning over raw graph text.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Optional

from .domain import LOCKED_STATUSES, EdgeKind, Layer, NodeType, Status, Verdict
from .repository import Repository

DEFAULT_THRESHOLDS = {"max_complexity": 7, "max_fan_out": 7, "max_loc": 300}
DONE_STATUSES = {Status.COMPLETED.value, Status.TESTED.value, Status.EVALUATED.value}


def thresholds(repo: Repository) -> dict:
    return {k: int(repo.get_meta(k, str(v))) for k, v in DEFAULT_THRESHOLDS.items()}


class GraphView:
    """In-memory snapshot of nodes/edges with component membership resolved once."""

    def __init__(self, repo: Repository):
        self.repo = repo
        self.nodes = {n["id"]: n for n in repo.list_nodes()}
        self.edges = repo.edges()
        self.parent = {e["to_id"]: e["from_id"] for e in self.edges if e["kind"] == EdgeKind.HAS.value}
        self.component = {nid: self._top(nid) for nid in self.nodes}

    def _top(self, nid: str) -> str:
        seen = set()
        while nid in self.parent and nid not in seen:
            seen.add(nid)
            nid = self.parent[nid]
        return nid

    def of_kind(self, *kinds: EdgeKind) -> list[dict]:
        values = {k.value for k in kinds}
        return [e for e in self.edges if e["kind"] in values]

    def is_code(self, nid: str) -> bool:
        return self.nodes[nid]["type"] != NodeType.COMPONENT.value


# ---------------------------------------------------------------------------
# Blast radius
# ---------------------------------------------------------------------------

def impact(repo: Repository, ref: str, depth: int = 3) -> dict:
    """Who is affected if `ref` changes: reverse traversal over CALLS/DEPENDS/IMPLEMENTS/USES."""
    g = GraphView(repo)
    root = repo.node(ref)
    scope = {root["id"], *repo.descendants(root["id"])}
    reverse = defaultdict(list)
    for e in g.of_kind(EdgeKind.CALLS, EdgeKind.DEPENDS, EdgeKind.IMPLEMENTS, EdgeKind.USES):
        # caller/dependent/implementer (from) is impacted when the target (to) changes
        reverse[e["to_id"]].append((e["from_id"], e))
    dist, via = {}, defaultdict(list)
    queue = deque((s, 0) for s in scope)
    while queue:
        nid, d = queue.popleft()
        if d >= depth:
            continue
        for src, e in reverse.get(nid, []):
            if src in scope:
                continue
            via[src].append({"kind": e["kind"], "to": nid, "function": e["function_name"] or None})
            if src not in dist:
                dist[src] = d + 1
                queue.append((src, d + 1))
    impacted = []
    for nid, d in sorted(dist.items(), key=lambda x: (x[1], x[0])):
        n = g.nodes[nid]
        impacted.append({"id": nid, "name": n["name"], "type": n["type"], "layer": n["layer"],
                         "status": n["status"], "component": g.component[nid], "distance": d,
                         "via": via[nid], "active_tasks": repo.active_tasks_for_node(nid)})
    contracts = [{"caller": e["from_id"], "callee": e["to_id"], "function": e["function_name"],
                  "signature": e["signature"]}
                 for e in g.of_kind(EdgeKind.CALLS) if e["to_id"] in scope and e["from_id"] not in scope]
    agents = sorted({t["agent"] for i in impacted for t in i["active_tasks"] if t.get("agent")})
    return {"node": root["id"], "scope": sorted(scope), "depth": depth, "contracts": contracts,
            "impacted": impacted, "impacted_components": sorted({i["component"] for i in impacted}),
            "locked_impacted": [i["id"] for i in impacted if Status(i["status"]) in LOCKED_STATUSES],
            "agents_to_notify": agents}


# ---------------------------------------------------------------------------
# Metrics and platform maturity
# ---------------------------------------------------------------------------

def _component_coupling(g: GraphView) -> dict[str, dict]:
    ca, ce = defaultdict(set), defaultdict(set)
    for e in g.of_kind(EdgeKind.CALLS, EdgeKind.DEPENDS, EdgeKind.IMPLEMENTS, EdgeKind.USES):
        a, b = g.component[e["from_id"]], g.component[e["to_id"]]
        if a != b:
            ce[a].add(b)
            ca[b].add(a)
    return {c: {"ca": len(ca[c]), "ce": len(ce[c])} for c in set(g.component.values())}


def metrics(repo: Repository) -> dict:
    g = GraphView(repo)
    fan = repo.fan_counts()
    coupling = _component_coupling(g)
    comps = [n for n in g.nodes.values() if n["type"] == NodeType.COMPONENT.value]
    code = [n for n in g.nodes.values() if n["type"] != NodeType.COMPONENT.value]
    adr_nodes = defaultdict(set)
    for a in repo.list_adrs():
        for nid in repo.adr(a["id"])["nodes"]:
            adr_nodes[g.component.get(nid, nid)].add(a["id"])

    per_component = []
    for c in comps:
        members = [n for n in code if g.component[n["id"]] == c["id"]]
        cx = [n["complexity"] for n in members if n["complexity"] is not None]
        ca, ce = coupling[c["id"]]["ca"], coupling[c["id"]]["ce"]
        inst = round(ce / (ca + ce), 2) if ca + ce else 0.0
        abst = round(sum(n["type"] == NodeType.INTERFACE.value for n in members) / len(members), 2) if members else 0.0
        per_component.append({
            "id": c["id"], "name": c["name"], "layer": c["layer"], "status": c["status"], "nodes": len(members),
            "status_counts": _count(members, "status"), "loc": sum(n["loc"] or 0 for n in members),
            "avg_complexity": round(sum(cx) / len(cx), 1) if cx else None, "max_complexity": max(cx) if cx else None,
            "change_count": sum(n["change_count"] for n in members) + c["change_count"],
            "fan_in": sum(fan.get(n["id"], {}).get("fan_in", 0) for n in members),
            "fan_out": sum(fan.get(n["id"], {}).get("fan_out", 0) for n in members),
            "afferent_coupling": ca, "efferent_coupling": ce, "instability": inst, "abstractness": abst,
            "distance_main_sequence": round(abs(abst + inst - 1), 2), "adrs": len(adr_nodes[c["id"]]),
        })

    done = [n for n in code if n["status"] in DONE_STATUSES]
    return {
        "project": repo.get_meta("project"), "design_locked": repo.get_meta("design_locked") == "1",
        "nodes": len(g.nodes), "code_nodes": len(code), "components": len(comps),
        "edges": _count(g.edges, "kind"), "status_counts": _count(code, "status"),
        "progress_pct": round(100 * len(done) / len(code), 1) if code else 0.0,
        "evaluated_pct": round(100 * sum(n["status"] == Status.EVALUATED.value for n in code) / len(code), 1)
        if code else 0.0,
        "loc": sum(n["loc"] or 0 for n in code),
        "tasks": _count(repo.list_tasks(), "status"), "adrs": _count(repo.list_adrs(), "status"),
        "platform_maturity": platform_maturity(repo, g, per_component),
        "components_detail": per_component,
    }


def platform_maturity(repo: Repository, g: GraphView, per_component: list[dict]) -> dict:
    """Signals that the platform is stabilising and use cases are built on top of it.

    - usecase_tasks_touching_platform_pct: of tasks touching USECASE nodes, how many also had to change
      PLATFORM nodes. Falling over time = platform absorbs new use cases without edits (the goal).
    - platform_instability_avg: Ce/(Ca+Ce) of platform components; platforms should be stable (-> 0).
    - platform_change_per_node: churn of platform code nodes.
    - platform_adrs: changes to baselined platform nodes.
    - dependency_direction_violations: PLATFORM -> USECASE edges (must be 0).
    """
    layer = {nid: n["layer"] for nid, n in g.nodes.items()}
    started = [t for t in repo.list_tasks() if t["started_at"]]
    uc_tasks = [t for t in started if any(layer.get(n) == Layer.USECASE.value for n in t["nodes"])]
    touching = [t for t in uc_tasks if any(layer.get(n) == Layer.PLATFORM.value for n in t["nodes"])]
    plat_comps = [c for c in per_component if c["layer"] == Layer.PLATFORM.value]
    plat_code = [n for n in g.nodes.values() if n["layer"] == Layer.PLATFORM.value and g.is_code(n["id"])]
    violations = [e for e in g.of_kind(EdgeKind.CALLS, EdgeKind.DEPENDS, EdgeKind.IMPLEMENTS, EdgeKind.USES)
                  if layer[e["from_id"]] == Layer.PLATFORM.value and layer[e["to_id"]] == Layer.USECASE.value]
    return {
        "usecase_tasks": len(uc_tasks),
        "usecase_tasks_touching_platform_pct": round(100 * len(touching) / len(uc_tasks), 1) if uc_tasks else None,
        "platform_instability_avg": round(sum(c["instability"] for c in plat_comps) / len(plat_comps), 2)
        if plat_comps else None,
        "platform_change_per_node": round(sum(n["change_count"] for n in plat_code) / len(plat_code), 2)
        if plat_code else None,
        "platform_evaluated_pct": round(100 * sum(n["status"] == Status.EVALUATED.value for n in plat_code)
                                        / len(plat_code), 1) if plat_code else None,
        "platform_adrs": sum(c["adrs"] for c in plat_comps),
        "dependency_direction_violations": len(violations),
    }


def _count(rows: list[dict], key: str) -> dict:
    out: dict = defaultdict(int)
    for r in rows:
        out[r[key]] += 1
    return dict(out)


# ---------------------------------------------------------------------------
# Deterministic architecture checks (ArchUnit-style, over the graph)
# ---------------------------------------------------------------------------

def check(repo: Repository) -> dict:
    g = GraphView(repo)
    t = thresholds(repo)
    fan = repo.fan_counts()
    findings: list[dict] = []

    def add(rule, severity, node, message):
        findings.append({"rule": rule, "severity": severity, "node": node, "message": message})

    deps = {(e["from_id"], e["to_id"]) for e in g.of_kind(EdgeKind.DEPENDS)}
    for e in g.of_kind(EdgeKind.CALLS, EdgeKind.DEPENDS, EdgeKind.IMPLEMENTS, EdgeKind.USES):
        a, b = g.nodes[e["from_id"]], g.nodes[e["to_id"]]
        if a["layer"] == Layer.PLATFORM.value and b["layer"] == Layer.USECASE.value:
            add("G01", "ERROR", a["id"], f"PLATFORM node depends on USECASE node '{b['id']}' ({e['kind']})")
        if e["kind"] not in (EdgeKind.CALLS.value, EdgeKind.USES.value):
            continue
        ca, cb = g.component[a["id"]], g.component[b["id"]]
        if ca != cb:
            if (ca, cb) not in deps:
                what = f"calls '{b['id']}.{e['function_name']}'" if e["function_name"] else f"uses type '{b['id']}'"
                add("G03", "WARN", a["id"], f"{what} across components without a declared DEPENDS {ca} -> {cb}")
            if e["kind"] != EdgeKind.CALLS.value:
                continue
            if b["type"] == NodeType.CLASS.value:  # utilities and config classes are designed to be shared
                add("G04", "WARN", a["id"], f"cross-component call targets concrete CLASS '{b['id']}'; "
                                            "depend on an INTERFACE or SERVICE_CLASS")

    for e in g.of_kind(EdgeKind.CALLS):  # G13: the called function must be on the target interface's contract
        target = g.nodes[e["to_id"]]
        contract = target.get("contract") or ""
        if target["type"] == NodeType.INTERFACE.value and contract and f"{e['function_name']}(" not in contract:
            add("G13", "WARN", e["from_id"], f"calls '{e['function_name']}' on interface '{target['id']}', "
                                             "which its contract does not declare (stale or undeclared)")

    for cycle in _component_cycles(g):
        add("G02", "ERROR", cycle[0], f"component dependency cycle: {' -> '.join(cycle + [cycle[0]])}")

    implemented = {e["to_id"] for e in g.of_kind(EdgeKind.IMPLEMENTS)}
    callees: dict[str, set] = defaultdict(set)
    for e in g.of_kind(EdgeKind.CALLS):
        callees[e["from_id"]].add(e["to_id"])
    for n in g.nodes.values():
        nid = n["id"]
        if not g.is_code(nid):
            continue
        if nid not in g.parent:
            add("G05", "WARN", nid, "code-level node has no parent (missing HAS edge)")
        if n["status"] in DONE_STATUSES:
            if not n["code_path"]:
                add("G06", "WARN", nid, f"{n['status']} but no code_path")
            if n["loc"] is None or n["complexity"] is None:
                add("G06", "INFO", nid, f"{n['status']} but loc/complexity not recorded")
            if n["type"] == NodeType.INTERFACE.value and nid not in implemented:
                add("G11", "WARN", nid, "interface has no IMPLEMENTS edge")
        if n["complexity"] is not None and n["complexity"] > t["max_complexity"]:
            add("G07", "WARN", nid, f"complexity {n['complexity']} > {t['max_complexity']}")
        collaborators = callees.get(nid, set())
        if len(collaborators) > t["max_fan_out"]:
            add("G08", "WARN", nid, f"calls {len(collaborators)} distinct collaborators > {t['max_fan_out']} "
                                    f"({fan.get(nid, {}).get('fan_out', 0)} function edges)")
        if n["loc"] is not None and n["loc"] > t["max_loc"]:
            add("G09", "WARN", nid, f"loc {n['loc']} > {t['max_loc']}")

    sev = _count(findings, "severity")
    return {"passed": sev.get("ERROR", 0) == 0, "summary": sev, "thresholds": t, "findings": findings}


def _component_cycles(g: GraphView) -> list[list[str]]:
    adj = defaultdict(set)
    for e in g.of_kind(EdgeKind.CALLS, EdgeKind.DEPENDS, EdgeKind.USES):
        a, b = g.component[e["from_id"]], g.component[e["to_id"]]
        if a != b:
            adj[a].add(b)
    index, low, stack, on, sccs, counter = {}, {}, [], set(), [], [0]

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in adj[v]:
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(sorted(comp))

    for v in list(adj):
        if v not in index:
            strong(v)
    return sccs


# ---------------------------------------------------------------------------
# Eval adherence (did coders follow the EVALs?)
# ---------------------------------------------------------------------------

def eval_report(repo: Repository, category: Optional[str] = None) -> dict:
    """first_pass_rate = share of (node, eval) pairs whose FIRST verdict was PASS.

    That is the "coder followed the eval without being told" signal. Low first_pass_rate
    evals are the ones whose guidance must move into coder prompts/skills.
    """
    evals = {e["id"]: e for e in repo.list_evals(category=category)}
    per_eval, per_coder = {}, defaultdict(lambda: {"results": 0, "first_pass": 0, "pairs": 0})
    for eid, ev in evals.items():
        results = repo.eval_results(eval_id=eid)
        pairs: dict[str, list[dict]] = defaultdict(list)
        for r in results:
            pairs[r["node_id"]].append(r)
        firsts = [rs[0] for rs in pairs.values()]
        first_pass = sum(r["verdict"] == Verdict.PASS.value for r in firsts)
        open_fail = sum(rs[-1]["verdict"] == Verdict.FAIL.value for rs in pairs.values())
        for r in firsts:
            c = per_coder[r.get("coder") or "unknown"]
            c["pairs"] += 1
            c["first_pass"] += r["verdict"] == Verdict.PASS.value
        for r in results:
            per_coder[r.get("coder") or "unknown"]["results"] += 1
        per_eval[eid] = {"category": ev["category"], "title": ev["title"], "severity": ev["severity"],
                         "results": len(results), "nodes": len(pairs), "open_fail": open_fail,
                         "first_pass_rate": round(first_pass / len(firsts), 2) if firsts else None,
                         **_count(results, "verdict")}
    for c in per_coder.values():
        c["first_pass_rate"] = round(c["first_pass"] / c["pairs"], 2) if c["pairs"] else None
    weakest = sorted((k for k, v in per_eval.items() if v["first_pass_rate"] is not None),
                     key=lambda k: (per_eval[k]["first_pass_rate"], -per_eval[k]["results"]))
    return {"evals": per_eval, "coders": dict(per_coder), "least_followed": weakest[:10],
            "never_checked": sorted(k for k, v in per_eval.items() if v["results"] == 0)}
