#!/usr/bin/env python
"""Replay a small orchestrated build on the sample project, so the UI has something real to show.

    python examples/demo.py                 # writes examples/demo.db
    python cg.py --db examples/demo.db serve --port 8770

The script plays the roles an agent team would: an orchestrator that seeds and locks a contract-first
design, coders that claim tasks and record their work, and reviewers that record EVAL verdicts. Along the
way it triggers the governance the tool enforces: a contract change blocked until an ADR is accepted, a
new node after the design lock, a review FAIL turned into a refinement, and the EVALUATED gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOL))

from codegraph.db import connect  # noqa: E402
from codegraph.domain import PolicyViolation  # noqa: E402
from codegraph.service import GraphService  # noqa: E402

ORCH = "orchestrator"
BASELINE = TOOL.parent / ".claude" / "skills" / "c4-design" / "reference" / "baseline-evals.json"
PROJECT_EVALS = [
    {"id": "BIZ-101", "category": "BUSINESS", "severity": "BLOCKER", "title": "Rate limit never exceeded",
     "rule": "Messages per recipient per day never exceed the channel's configured quota, including concurrent dispatches.",
     "check_method": "Property test over simulated bursts."},
    {"id": "APP-101", "category": "APP_DESIGN", "severity": "MAJOR", "title": "New channel = new plugin only",
     "rule": "Adding a delivery channel touches only a plugin file and plugins.json.",
     "check_method": "List the files a new channel plugin touches."},
    {"id": "PERF-101", "category": "PERFORMANCE", "severity": "MAJOR", "title": "Per-event path is O(1)",
     "rule": "SubscriptionFilter + Dispatcher.dispatch do no I/O and no scans per event.",
     "check_method": "Read the dispatch call chain; benchmark 100k events."},
]
FALLBACK_EVALS = [
    {"id": "ARCH-001", "category": "ARCH", "title": "Platform never depends on use case", "rule": "No PLATFORM node depends on a USECASE node."},
    {"id": "APP-001", "category": "APP_DESIGN", "title": "Single responsibility", "rule": "A class does what its business intent says."},
    {"id": "CODE-001", "category": "CODE", "title": "Contract functions are unit tested", "rule": "Every function with an incoming CALLS edge has tests."},
]
REVIEW = {  # reviewer -> EVAL ids it applies in this demo
    "arch-reviewer": ["ARCH-001", "ARCH-003", "ARCH-004", "ARCH-006"],
    "app-design-reviewer": ["APP-001", "APP-002", "APP-003"],
    "code-reviewer": ["CODE-001", "CODE-002", "CODE-004", "BIZ-001"],
}


def say(text: str) -> None:
    print(f"\n== {text}")


def build(svc: GraphService, nodes: list[str], task: str, agent: str, sizes: dict[str, tuple[int, int]]) -> None:
    """A coder finishing its nodes: record size and complexity, then COMPLETED and TESTED."""
    for n in nodes:
        loc, cx = sizes.get(n, (60, 3))
        svc.update_node(n, {"loc": loc, "complexity": cx}, actor=agent, task_id=task)
        svc.set_status(n, "COMPLETED", actor=agent, task_id=task)
        svc.set_status(n, "TESTED", actor=agent, task_id=task)


def review(svc: GraphService, nodes: list[str], task: str, fails: dict[tuple[str, str], str] | None = None) -> None:
    known = {e["id"] for e in svc.list_evals()}
    for reviewer, evals in REVIEW.items():
        for n in nodes:
            for ev in evals:
                if ev not in known:
                    continue
                note = (fails or {}).get((n, ev))
                svc.record_eval(ev, n, "FAIL" if note else "PASS", notes=note, task_id=task, actor=reviewer)


def blocked(fn, *args, **kwargs) -> dict:
    try:
        fn(*args, **kwargs)
    except PolicyViolation as e:
        print("   exit 3 ->", json.dumps(e.to_dict())[:400], "...")
        return e.details
    raise AssertionError("expected the tool to block this change")


def run(db_path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(str(db_path) + suffix).unlink(missing_ok=True)
    svc = GraphService(connect(str(db_path)))
    seed = json.loads((TOOL / "examples" / "sample_seed.json").read_text(encoding="utf-8"))

    say("Orchestrator: import the contract-first C4 design, the EVAL catalog, and lock the design")
    svc.init_project(seed["project"], actor=ORCH)
    print("  ", svc.import_seed(seed, actor=ORCH))
    evals = json.loads(BASELINE.read_text(encoding="utf-8"))["evals"] if BASELINE.exists() else FALLBACK_EVALS
    print("   evals:", svc.import_evals(evals + PROJECT_EVALS, actor=ORCH)["imported"])
    print("   check:", svc.check()["summary"] or "clean")
    svc.set_design_lock(True, actor=ORCH)

    say("Three coders take tasks in parallel (no shared nodes)")
    cfg = ["config_manager.config_library", "config_manager.config_repository",
           "config_manager.sqlite_config_repository", "config_manager.channel_config"]
    eng = ["dispatch_engine.channel", "dispatch_engine.routing_rule", "dispatch_engine.plugin_loader", "dispatch_engine.dispatcher"]
    intake = ["event_intake.event_source", "event_intake.simulated_event_source", "event_intake.subscription_filter"]
    t1 = svc.create_task("Config library and repository", nodes=",".join(cfg), agent="coder-1", actor=ORCH,
                         description="1. Add/get/delete configs. 2. Resolve a channel's config with defaults. 3. SQLite adapter.")["id"]
    t2 = svc.create_task("Dispatch engine core", nodes=",".join(eng), agent="coder-2", actor=ORCH,
                         description="1. Plugin loader from plugins.json. 2. Dispatcher enforces the per-recipient quota (BIZ-101).")["id"]
    t3 = svc.create_task("Event intake", nodes=",".join(intake), agent="coder-3", actor=ORCH,
                         description="1. EventSource port + simulator. 2. Subscription rules as a chain.")["id"]
    for t, agent in ((t1, "coder-1"), (t2, "coder-2"), (t3, "coder-3")):
        svc.start_task(t, agent=agent, actor=agent)

    say("A coder tries to edit a node another task owns: blocked")
    blocked(svc.update_node, "dispatch_engine.dispatcher", {"complexity": 4}, actor="coder-3", task_id=t3)

    say("Coders record their work: sizes, complexity, USES edges, status")
    svc.find_utilities("render template")
    svc.upsert_edge("USES", "dispatch_engine.dispatcher", "config_manager.channel_config", actor="coder-2", task_id=t2)
    build(svc, cfg, t1, "coder-1", {"config_manager.config_library": (118, 4), "config_manager.sqlite_config_repository": (74, 3),
                                     "config_manager.channel_config": (41, 1), "config_manager.config_repository": (18, 1)})
    build(svc, eng, t2, "coder-2", {"dispatch_engine.dispatcher": (164, 6), "dispatch_engine.plugin_loader": (88, 4),
                                     "dispatch_engine.channel": (24, 1), "dispatch_engine.routing_rule": (16, 1)})
    svc.update_node("event_intake.event_source", {"loc": 20, "complexity": 1}, actor="coder-3", task_id=t3)
    svc.set_status("event_intake.event_source", "COMPLETED", actor="coder-3", task_id=t3)
    for t, agent in ((t1, "coder-1"), (t2, "coder-2")):
        svc.finish_task(t, "Implemented with unit tests.", actor=agent)

    say("Reviewers record verdicts; one FAIL on the config library, one on the dispatcher")
    review(svc, cfg, t1, {("config_manager.config_library", "CODE-001"):
                          "library.py:52 resolve() has no test for a missing default group; add boundary tests."})
    review(svc, eng, t2, {("dispatch_engine.dispatcher", "CODE-004"):
                          "dispatcher.py:88 bare except swallows plugin errors; log and surface them with context."})
    print("   gate:", end=" ")
    blocked(svc.set_status, "config_manager.config_library", "EVALUATED", actor=ORCH)

    say("Refinement task fixes the config library finding, re-review passes, nodes gated to EVALUATED")
    t4 = svc.create_task("Fix CODE-001 on ConfigLibrary", nodes="config_manager.config_library", kind="REFINEMENT",
                         agent="coder-1", actor=ORCH, description="Add boundary tests for resolve() (missing default group).")["id"]
    svc.start_task(t4, agent="coder-1", actor="coder-1")
    svc.set_status("config_manager.config_library", "TESTED", actor="coder-1", task_id=t4)
    svc.finish_task(t4, "Boundary tests added.", actor="coder-1")
    svc.record_eval("CODE-001", "config_manager.config_library", "PASS", task_id=t4, actor="code-reviewer")
    for n in cfg + ["dispatch_engine.channel", "dispatch_engine.routing_rule", "dispatch_engine.plugin_loader"]:
        svc.set_status(n, "EVALUATED", actor=ORCH)

    say("A use-case coder needs a new function on the EVALUATED ConfigLibrary: the tool stops it")
    t5 = svc.create_task("Email channel plugin", nodes="email_channel.email_sender,email_channel.quiet_hours_rule",
                         agent="coder-4", actor=ORCH, description="1. Email plugin via the Channel port. 2. Quiet hours rule.")["id"]
    svc.start_task(t5, agent="coder-4", actor="coder-4")
    sig = "get_templates(channel_id: str) -> list[Template]"
    details = blocked(svc.upsert_edge, "CALLS", "email_channel.email_sender", "config_manager.config_library",
                      function_name="get_templates", signature=sig, purpose="Load message templates.",
                      actor="coder-4", task_id=t5)
    adr = svc.propose_adr("Expose message templates on ConfigLibrary", nodes="config_manager.config_library", actor="coder-4",
                          context="The email channel needs per-channel templates; ConfigLibrary is EVALUATED and has no such function.",
                          decision="Add get_templates(channel_id) -> list[Template] to ConfigLibrary (templates are a config group); "
                                   "email_channel declares a dependency on config_manager.",
                          consequences=f"Callee changes; impacted: {[i.get('callee') or i.get('caller') for i in details['impacted']]}.")["id"]
    svc.block_task(t5, f"{adr}: needs get_templates on ConfigLibrary", actor="coder-4")
    svc.decide_adr(adr, "ACCEPTED", note="Additive, inside the approved design.", actor=ORCH)
    svc.upsert_edge("CALLS", "email_channel.email_sender", "config_manager.config_library", function_name="get_templates",
                    signature=sig, purpose="Load message templates.", actor="coder-4", task_id=t5, adr_id=adr)
    svc.upsert_edge("DEPENDS", "email_channel", "config_manager", actor=ORCH, adr_id=adr)
    svc.start_task(t5, agent="coder-4", actor="coder-4")
    t6 = svc.create_task("Add get_templates to ConfigLibrary", nodes="config_manager.config_library", agent="coder-1",
                         adr_id=adr, actor=ORCH, description=f"Implement {sig} under {adr}.")["id"]
    svc.start_task(t6, agent="coder-1", actor="coder-1")
    svc.update_node("config_manager.config_library", {"contract": "get_channel_config(channel_id) -> ChannelConfig; "
                                                      "get_templates(channel_id) -> list[Template]"}, actor="coder-1", task_id=t6)

    say("After the design lock, a new SMS channel needs an ADR before its nodes can exist")
    blocked(svc.add_node, {"id": "sms_channel", "name": "SMS Channel", "type": "COMPONENT", "layer": "USECASE"}, actor=ORCH)
    adr2 = svc.propose_adr("Add an SMS channel plugin", actor=ORCH, context="Product asked for SMS alerts.",
                           decision="New USECASE component sms_channel with SmsSender implementing Channel.",
                           consequences="No platform change: plugin file + plugins.json entry only.")["id"]
    svc.decide_adr(adr2, "ACCEPTED", note="Use case only; platform untouched.", actor=ORCH)
    svc.add_node({"id": "sms_channel", "name": "SMS Channel", "type": "COMPONENT", "layer": "USECASE",
                  "business_intent": "Short transactional messages over an SMS gateway.", "code_path": "plugins/sms_channel"},
                 actor=ORCH, adr_id=adr2)
    svc.add_node({"id": "sms_channel.sms_sender", "name": "SmsSender", "type": "CLASS", "parent": "sms_channel",
                  "business_intent": "SMS channel plugin.", "code_path": "plugins/sms_channel/sender.py::SmsSender"},
                 actor=ORCH, adr_id=adr2)
    svc.upsert_edge("DEPENDS", "sms_channel", "dispatch_engine", actor=ORCH, adr_id=adr2)
    svc.upsert_edge("IMPLEMENTS", "sms_channel.sms_sender", "dispatch_engine.channel", actor=ORCH, adr_id=adr2)

    m = svc.metrics()
    say("Where things stand")
    print("   status:", m["status_counts"], "| progress", m["progress_pct"], "% | evaluated", m["evaluated_pct"], "%")
    print("   platform maturity:", m["platform_maturity"])
    print("   check:", svc.check()["summary"] or "clean")
    print("   EVAL first-pass (least followed):", svc.eval_report()["least_followed"][:3])
    print(f"\nOpen the UI:  python {TOOL / 'cg.py'} --db {db_path} serve --port 8770")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=TOOL / "examples" / "demo.db")
    run(ap.parse_args().db.resolve())
