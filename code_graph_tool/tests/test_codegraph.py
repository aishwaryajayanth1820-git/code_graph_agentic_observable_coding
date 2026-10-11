import json
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOL))

from codegraph.db import connect  # noqa: E402
from codegraph.domain import PolicyViolation, ValidationError  # noqa: E402
from codegraph.service import GraphService  # noqa: E402

SEED = json.loads((TOOL / "examples" / "sample_seed.json").read_text(encoding="utf-8"))
ORCH = "orchestrator"


@pytest.fixture
def svc():
    s = GraphService(connect(":memory:"))
    s.import_seed(SEED, actor=ORCH)
    return s


def accepted_adr(svc, nodes, title="change"):
    adr = svc.propose_adr(title, context="c", decision="d", nodes=nodes, actor="coder-1")
    return svc.decide_adr(adr["id"], "ACCEPTED", actor=ORCH)["id"]


def started_task(svc, nodes, agent="coder-1", kind="FEATURE"):
    t = svc.create_task("work", description="ctx", nodes=nodes, agent=agent, kind=kind, actor=ORCH)
    return svc.start_task(t["id"], agent=agent, actor=agent)["id"]


# ---- structure ---------------------------------------------------------------

def test_seed_builds_hierarchy_and_fan_counts(svc):
    n = svc.get_node("dispatch_engine.dispatcher")
    assert n["parent"] == "dispatch_engine" and n["component"] == "dispatch_engine"
    assert n["fan_out"] == 3 and n["fan_in"] == 1
    assert svc.get_node("Dispatcher")["id"] == n["id"]  # lookup by name


def test_structural_rules(svc):
    with pytest.raises(ValidationError):  # HAS must go down the C4 levels
        svc.upsert_edge("HAS", "config_manager.config_library", "dispatch_engine", actor=ORCH)
    with pytest.raises(ValidationError):  # CALLS needs a signature
        svc.upsert_edge("CALLS", "email_channel.email_sender", "dispatch_engine.routing_rule", function_name="x", actor=ORCH)
    with pytest.raises(ValidationError):  # no CALLS on components
        svc.upsert_edge("CALLS", "email_channel", "dispatch_engine", function_name="x", signature="x()", actor=ORCH)
    with pytest.raises(ValidationError):  # DEPENDS stays within a C4 level
        svc.upsert_edge("DEPENDS", "email_channel", "dispatch_engine.routing_rule", actor=ORCH)
    with pytest.raises(ValidationError):  # duplicate name
        svc.add_node({"id": "x", "name": "ConfigLibrary", "type": "CLASS", "layer": "PLATFORM"}, actor=ORCH)


def test_status_aliases_and_layer_inheritance(svc):
    n = svc.add_node({"id": "email_channel.x", "name": "X", "type": "CLASS", "parent": "email_channel", "status": "PLANED"},
                     actor=ORCH)
    assert n["layer"] == "USECASE" and n["status"] == "PLANNED"


# ---- tasks and change count ----------------------------------------------------

def test_task_start_counts_change_once(svc):
    tid = started_task(svc, "email_channel.email_sender")
    assert svc.get_node("email_channel.email_sender")["change_count"] == 1
    assert svc.get_node("email_channel.email_sender")["status"] == "IN_PROGRESS"
    svc.block_task(tid, "waiting on ADR", actor="coder-1")
    svc.start_task(tid, actor="coder-1")  # resume does not recount
    assert svc.get_node("email_channel.email_sender")["change_count"] == 1


def test_node_cannot_be_owned_by_two_active_tasks(svc):
    started_task(svc, "email_channel.email_sender", agent="coder-1")
    t2 = svc.create_task("other", nodes="email_channel.email_sender", agent="coder-2", actor=ORCH)
    with pytest.raises(PolicyViolation) as e:
        svc.start_task(t2["id"], actor="coder-2")
    assert e.value.rule == "OWNERSHIP"


def test_other_task_cannot_edit_owned_node(svc):
    started_task(svc, "email_channel.email_sender", agent="coder-1")
    t2 = started_task(svc, "email_channel.quiet_hours_rule", agent="coder-2")
    with pytest.raises(PolicyViolation):
        svc.update_node("email_channel.email_sender", {"loc": 10}, actor="coder-2", task_id=t2)


# ---- ADR governance --------------------------------------------------------------

def _to_tested(svc, node, agent="coder-1"):
    tid = started_task(svc, node, agent=agent)
    svc.set_status(node, "COMPLETED", actor=agent, task_id=tid)
    svc.set_status(node, "TESTED", actor=agent, task_id=tid)
    svc.finish_task(tid, "done", actor=agent)
    return tid


def test_locked_node_needs_accepted_adr(svc):
    node = "config_manager.config_library"
    _to_tested(svc, node)
    t = svc.create_task("change", nodes=node, agent="coder-2", actor=ORCH)
    with pytest.raises(PolicyViolation) as e:
        svc.start_task(t["id"], actor="coder-2")
    assert e.value.rule == "LOCKED_NODE" and "next_step" in e.value.details
    adr = svc.propose_adr("extend", context="c", decision="d", nodes=node, actor="coder-2")
    with pytest.raises(PolicyViolation):  # proposed is not enough
        svc.start_task(t["id"], actor="coder-2", adr_id=adr["id"])
    with pytest.raises(PolicyViolation):  # coders cannot approve
        svc.decide_adr(adr["id"], "ACCEPTED", actor="coder-2")
    svc.decide_adr(adr["id"], "ACCEPTED", actor=ORCH)
    svc.start_task(t["id"], actor="coder-2", adr_id=adr["id"])
    assert svc.get_node(node)["change_count"] == 2


def test_refinement_on_tested_node_with_open_fail_skips_adr(svc):
    node = "config_manager.config_library"
    _to_tested(svc, node)
    svc.upsert_eval({"id": "ARCH-001", "category": "ARCH", "title": "t", "rule": "r"}, actor=ORCH)
    svc.record_eval("ARCH-001", node, "FAIL", notes="leaks sqlite row types", actor="arch-reviewer")
    t = svc.create_task("fix review", nodes=node, kind="REFINEMENT", agent="coder-1", actor=ORCH)
    assert svc.start_task(t["id"], actor="coder-1")["status"] == "IN_PROGRESS"


def test_design_lock_requires_adr_for_new_nodes(svc):
    with pytest.raises(PolicyViolation):
        svc.set_design_lock(True, actor="coder-1")
    svc.set_design_lock(True, actor=ORCH)
    new = {"id": "email_channel.y", "name": "Y", "type": "CLASS", "parent": "email_channel"}
    with pytest.raises(PolicyViolation) as e:
        svc.add_node(new, actor="coder-1")
    assert e.value.rule == "DESIGN_LOCK"
    adr = accepted_adr(svc, [])
    assert svc.add_node(new, actor="coder-1", adr_id=adr)["adrs"][0]["id"] == adr


# ---- contract changes between parallel agents ---------------------------------

def test_signature_change_on_seeded_contract_needs_adr(svc):
    tid = started_task(svc, "dispatch_engine.dispatcher")
    with pytest.raises(PolicyViolation) as e:
        svc.upsert_edge("CALLS", "dispatch_engine.dispatcher", "config_manager.config_library",
                        function_name="get_channel_config", signature="get_channel_config(cid: int) -> dict",
                        actor="coder-1", task_id=tid)
    assert e.value.rule == "CONTRACT_CHANGE"
    assert any(i.get("callee") == "config_manager.config_library" for i in e.value.details["impacted"])


def test_own_draft_edge_may_change_freely(svc):
    tid = started_task(svc, "email_channel.email_sender")
    kw = dict(function_name="notify", actor="coder-1", task_id=tid)
    svc.upsert_edge("CALLS", "email_channel.email_sender", "email_channel.quiet_hours_rule", signature="notify() -> None", **kw)
    out = svc.upsert_edge("CALLS", "email_channel.email_sender", "email_channel.quiet_hours_rule",
                          signature="notify(n: int) -> None", **kw)
    assert out["contract_changed"] is True
    svc.delete_edge("CALLS", "email_channel.email_sender", "email_channel.quiet_hours_rule", function_name="notify",
                    actor="coder-1", task_id=tid)


def test_new_function_on_foreign_owned_callee_needs_adr_but_reuse_is_fine(svc):
    started_task(svc, "config_manager.config_library", agent="coder-1")
    t2 = started_task(svc, "event_intake.subscription_filter", agent="coder-2")
    with pytest.raises(PolicyViolation):
        svc.upsert_edge("CALLS", "event_intake.subscription_filter", "config_manager.config_library",
                        function_name="quota", signature="quota(cid: str) -> int", actor="coder-2", task_id=t2)
    # reusing the existing contract exactly is not a change
    out = svc.upsert_edge("CALLS", "event_intake.subscription_filter", "config_manager.config_library",
                          function_name="get_channel_config",
                          signature="get_channel_config(channel_id: str) -> ChannelConfig",
                          actor="coder-2", task_id=t2)
    assert out["created"] is True


# ---- lifecycle gate ---------------------------------------------------------------

def test_evaluated_gate(svc):
    node = "email_channel.quiet_hours_rule"
    with pytest.raises(PolicyViolation):
        svc.set_status(node, "EVALUATED", actor=ORCH)
    _to_tested(svc, node)
    with pytest.raises(PolicyViolation):  # no eval results yet
        svc.set_status(node, "EVALUATED", actor=ORCH)
    svc.upsert_eval({"id": "CODE-001", "category": "CODE", "title": "t", "rule": "r"}, actor=ORCH)
    svc.record_eval("CODE-001", node, "FAIL", notes="missing tests", actor="code-reviewer")
    with pytest.raises(PolicyViolation):
        svc.set_status(node, "EVALUATED", actor=ORCH)
    svc.record_eval("CODE-001", node, "PASS", actor="code-reviewer")
    assert svc.set_status(node, "EVALUATED", actor=ORCH)["status"] == "EVALUATED"
    with pytest.raises(ValidationError):
        svc.record_eval("CODE-001", node, "FAIL", actor="code-reviewer")  # FAIL needs notes


# ---- utilities --------------------------------------------------------------------

def test_utility_reuse(svc):
    found = svc.find_utilities("render template")
    assert [u["name"] for u in found["matches"]] == ["render_template"]
    with pytest.raises(ValidationError):
        svc.add_utility("render_template", "dup", actor="coder-1")


# ---- analytics --------------------------------------------------------------------

def test_impact_of_interface_reaches_implementers_and_callers(svc):
    started_task(svc, "email_channel.email_sender", agent="coder-7")
    out = svc.impact("dispatch_engine.channel")
    ids = {i["id"] for i in out["impacted"]}
    assert {"email_channel.email_sender", "dispatch_engine.dispatcher"} <= ids
    assert "coder-7" in out["agents_to_notify"]


def test_check_flags_layer_violation_cycle_and_undeclared_dependency(svc):
    assert svc.check()["passed"] is True
    svc.upsert_edge("CALLS", "dispatch_engine.dispatcher", "email_channel.email_sender", function_name="peek",
                    signature="peek() -> int", actor=ORCH)
    rules = {f["rule"] for f in svc.check()["findings"]}
    assert {"G01", "G02", "G03", "G04"} <= rules


def test_metrics_platform_maturity(svc):
    started_task(svc, "email_channel.email_sender,dispatch_engine.plugin_loader", agent="coder-1")
    started_task(svc, "email_channel.quiet_hours_rule", agent="coder-2")
    m = svc.metrics()
    assert m["platform_maturity"]["usecase_tasks_touching_platform_pct"] == 50.0
    comp = {c["id"]: c for c in m["components_detail"]}
    assert comp["config_manager"]["instability"] == 0.0  # only depended upon
    assert comp["email_channel"]["instability"] == 1.0


def test_eval_report_first_pass_rate(svc):
    svc.upsert_eval({"id": "ARCH-001", "category": "ARCH", "title": "t", "rule": "r"}, actor=ORCH)
    svc.record_eval("ARCH-001", "email_channel.email_sender", "FAIL", notes="n", coder="coder-1", actor="rev")
    svc.record_eval("ARCH-001", "email_channel.email_sender", "PASS", coder="coder-1", actor="rev")
    svc.record_eval("ARCH-001", "email_channel.quiet_hours_rule", "PASS", coder="coder-2", actor="rev")
    r = svc.eval_report()
    assert r["evals"]["ARCH-001"]["first_pass_rate"] == 0.5
    assert r["coders"]["coder-1"]["first_pass_rate"] == 0.0


def test_export_import_roundtrip(svc):
    doc = svc.export_seed()
    other = GraphService(connect(":memory:"))
    other.import_seed(doc, actor=ORCH)
    assert len(other.export_seed()["edges"]) == len(doc["edges"])
    assert svc.import_seed(doc, actor=ORCH)["nodes_created"] == 0  # idempotent


def test_scan_loc_counts_python_class(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.py").write_text("class A:\n    def f(self):\n        return 1\n\n\nclass B:\n    pass\n")
    s = GraphService(connect(":memory:"), project_root=tmp_path)
    s.add_node({"id": "c", "name": "C", "type": "COMPONENT", "layer": "PLATFORM"}, actor=ORCH)
    s.add_node({"id": "a", "name": "A", "type": "CLASS", "parent": "c", "code_path": "src/m.py::A"}, actor=ORCH)
    assert s.scan_loc()["updated"] == [{"id": "a", "from": None, "to": 3}]


def test_uses_edges_make_shared_types_visible_in_impact(svc):
    svc.add_node({"id": "config_manager.models", "name": "ConfigModelsX", "type": "CONFIG_CLASS",
                  "parent": "config_manager"}, actor=ORCH)
    assert svc.impact("config_manager.models")["impacted"] == []
    svc.upsert_edge("USES", "email_channel.email_sender", "config_manager.models", actor=ORCH)
    out = svc.impact("config_manager.models")
    assert [i["id"] for i in out["impacted"]] == ["email_channel.email_sender"]
    assert any(f["rule"] == "G03" and "uses type" in f["message"] for f in svc.check()["findings"])
    with pytest.raises(ValidationError):
        svc.upsert_edge("USES", "email_channel", "config_manager.models", actor=ORCH)


def test_g08_counts_distinct_collaborators_not_function_edges(svc):
    for i in range(9):  # 9 functions on one collaborator: chatty contract, not wide coupling
        svc.upsert_edge("CALLS", "email_channel.email_sender", "dispatch_engine.routing_rule", function_name=f"f{i}",
                        signature=f"f{i}() -> None", actor=ORCH)
    assert not any(f["rule"] == "G08" for f in svc.check()["findings"])
    assert svc.get_node("email_channel.email_sender")["fan_out"] == 10


def test_scan_loc_scoped_to_task(tmp_path):
    (tmp_path / "a.py").write_text("x = 1" + chr(10) + "y = 2" + chr(10))
    s = GraphService(connect(":memory:"), project_root=tmp_path)
    s.add_node({"id": "c", "name": "C", "type": "COMPONENT", "layer": "PLATFORM"}, actor=ORCH)
    for nid in ("a", "b"):
        s.add_node({"id": nid, "name": nid.upper(), "type": "CLASS", "parent": "c", "code_path": "a.py"}, actor=ORCH)
    t = s.create_task("t", nodes="a", actor=ORCH)
    assert [u["id"] for u in s.scan_loc(task_id=t["id"])["updated"]] == ["a"]


def test_g13_flags_calls_to_functions_missing_from_interface_contract(svc):
    svc.update_node("dispatch_engine.channel", {"contract": "configure(config); send(message) -> DeliveryResult"}, actor=ORCH)
    assert not any(f["rule"] == "G13" for f in svc.check()["findings"])
    svc.upsert_edge("CALLS", "dispatch_engine.dispatcher", "dispatch_engine.channel", function_name="ghost",
                    signature="ghost() -> None", actor=ORCH)
    assert any(f["rule"] == "G13" and "ghost" in f["message"] for f in svc.check()["findings"])


# ---- adapters ---------------------------------------------------------------------

def test_cli_policy_violation_exit_code(tmp_path, capsys):
    from codegraph.cli import main
    db = str(tmp_path / "g.db")
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps(SEED))
    assert main(["--db", db, "--actor", ORCH, "import", str(seed)]) == 0
    assert main(["design", "lock", "--db", db, "--actor", "coder-1"]) == 3  # options after the subcommand work too
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == "POLICY_VIOLATION"


def test_install_carries_license_and_notice_not_the_host_projects(tmp_path):
    from codegraph.installer import install
    repo = tmp_path / "repo"
    tool = repo / "code_graph_tool"
    tool.mkdir(parents=True)
    (tool / "cg.py").write_text("# cli")
    (repo / "LICENSE").write_text("Apache License")
    (repo / "NOTICE").write_text("Code Graph: notice")
    host = tmp_path / "host"
    host.mkdir()
    (host / "LICENSE").write_text("host license")
    install(tool, host)
    assert (host / "code_graph" / "NOTICE").read_text().startswith("Code Graph")
    assert (host / "code_graph" / "LICENSE").read_text() == "Apache License"
    nested = host / "sub"
    nested.mkdir()
    install(host / "code_graph", nested)  # from an installed copy: its own legal files, never the host's
    assert (nested / "code_graph" / "LICENSE").read_text() == "Apache License"


def test_api_smoke(tmp_path):
    import asyncio

    import httpx

    from codegraph.api import create_app
    db = str(tmp_path / "g.db")
    s = GraphService(connect(db))
    s.import_seed(SEED, actor=ORCH)
    app = create_app(db, ui_dir=TOOL / "ui")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            g = (await client.get("/api/graph")).json()
            assert len(g["nodes"]) == len(SEED["nodes"]) and all(e["kind"] != "HAS" for e in g["edges"])
            assert (await client.get("/api/nodes/dispatch_engine.dispatcher")).json()["fan_out"] == 3
            r = await client.post("/api/adrs/ADR-9999/decide", json={"status": "ACCEPTED"}, headers={"X-Actor": "human"})
            assert r.status_code == 404
            r = await client.post("/api/tasks", json={"title": "t", "nodes": "email_channel"}, headers={"X-Actor": ORCH})
            assert r.json()["id"] == "T-0001"
            assert (await client.get("/ui/")).status_code == 200

    asyncio.run(scenario())
