"""Structural validation and governance policies.

Structural rules keep the graph well-formed (always enforced).
Policies encode the development governance: ADRs for baselined nodes,
contract-change escalation between parallel agents, design lock, ownership.

Extension point: implement `Policy.check` and pass your list to
`GraphService(policies=...)`. A policy raises `PolicyViolation` to block.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .domain import (C4_RANK, CONTENT_FIELDS, LOCKED_STATUSES, STATUS_ORDER, AdrStatus, EdgeKind, NodeType,
                     PolicyViolation, Status, TaskKind, ValidationError, Verdict)
from .repository import Repository


# ---------------------------------------------------------------------------
# Structural rules
# ---------------------------------------------------------------------------

def rank(node: dict) -> int:
    return C4_RANK[NodeType(node["type"])]


def validate_edge(repo: Repository, kind: EdgeKind, src: dict, dst: dict, function_name: str, signature: Optional[str]):
    if src["id"] == dst["id"]:
        raise ValidationError("self-edges are not allowed (internal calls are not graph edges)")
    if kind is EdgeKind.HAS:
        if rank(src) >= rank(dst):
            raise ValidationError(f"HAS must go from a higher C4 level to a lower one "
                                  f"({src['type']} -> {dst['type']} is not allowed)")
        parent = repo.parent_of(dst["id"])
        if parent and parent["id"] != src["id"]:
            raise ValidationError(f"'{dst['id']}' already belongs to '{parent['id']}' (one parent per node)")
    elif kind is EdgeKind.DEPENDS:
        if rank(src) != rank(dst):
            raise ValidationError("DEPENDS connects nodes of the same C4 level "
                                  f"({src['type']} -> {dst['type']}); use CALLS between classes")
    elif kind is EdgeKind.CALLS:
        if NodeType.COMPONENT.value in (src["type"], dst["type"]):
            raise ValidationError("CALLS connects code-level nodes (classes/services/interfaces), not COMPONENTs")
        if not function_name:
            raise ValidationError("CALLS edge needs a function name (--fn)")
        if not signature:
            raise ValidationError("CALLS edge needs a function signature (--sig)")
    elif kind is EdgeKind.USES:
        if NodeType.COMPONENT.value in (src["type"], dst["type"]):
            raise ValidationError("USES connects code-level nodes (the importer and the shared type)")
    elif kind is EdgeKind.IMPLEMENTS:
        if dst["type"] != NodeType.INTERFACE.value or src["type"] == NodeType.COMPONENT.value:
            raise ValidationError("IMPLEMENTS goes from a code-level node to an INTERFACE")


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

@dataclass
class ChangeContext:
    action: str  # node.create | node.update | node.status | node.delete | edge.upsert | edge.delete | task.start | task.add_node
    actor: Optional[str]
    task_id: Optional[str]
    adr_id: Optional[str]
    node: Optional[dict] = None              # node being changed (for edges: the caller / from node)
    fields: dict = field(default_factory=dict)
    edge: Optional[dict] = None              # proposed edge
    existing_edge: Optional[dict] = None
    target: Optional[dict] = None            # edge to-node
    task: Optional[dict] = None


class Policy:
    name = "policy"

    def check(self, ctx: ChangeContext, repo: Repository) -> None:  # pragma: no cover - interface
        raise NotImplementedError


def _is_approver(repo: Repository, actor: Optional[str]) -> bool:
    approvers = {a.strip() for a in (repo.get_meta("approvers") or "").split(",") if a.strip()}
    return bool(actor) and actor in approvers


def require_adr(repo: Repository, ctx: ChangeContext, node_ids: list[str], rule: str, message: str,
                details: Optional[dict] = None) -> None:
    """Pass only if ctx carries an ACCEPTED ADR linked to every node in node_ids."""
    hint = {"next_step": "Propose an ADR (cg adr propose --title ... --context ... --decision ... "
                         f"--nodes {','.join(node_ids) or '<new-node-id>'}), stop, and escalate the ADR id "
                         "to the orchestrator. Retry with --adr <id> once it is ACCEPTED."}
    if not ctx.adr_id:
        raise PolicyViolation(rule, message, {**(details or {}), **hint})
    adr = repo.adr(ctx.adr_id)
    if adr["status"] != AdrStatus.ACCEPTED.value:
        raise PolicyViolation(rule, f"{message} ({ctx.adr_id} is {adr['status']}, needs ACCEPTED)",
                              {**(details or {}), **hint})
    missing = [n for n in node_ids if n not in adr["nodes"]]
    if missing:
        raise PolicyViolation(rule, f"{ctx.adr_id} does not cover node(s) {missing}",
                              {**(details or {}), "next_step": "Ask the orchestrator to link the ADR: "
                               f"cg adr link {ctx.adr_id} {','.join(missing)}"})


class DesignLockPolicy(Policy):
    """After the C4 design is baselined (`cg design lock`), adding/removing nodes needs an ADR."""
    name = "DESIGN_LOCK"

    def check(self, ctx, repo):
        if ctx.action not in ("node.create", "node.delete") or repo.get_meta("design_locked") != "1":
            return
        nodes = [] if ctx.action == "node.create" else [ctx.node["id"]]
        require_adr(repo, ctx, nodes, self.name, f"design is locked: {ctx.action} needs an accepted ADR")


class LockedNodePolicy(Policy):
    """TESTED/EVALUATED nodes are baselined: changing them needs an ADR (review refinements excepted)."""
    name = "LOCKED_NODE"
    ACTIONS = ("node.update", "node.delete", "task.start", "task.add_node", "edge.upsert", "edge.delete")

    def check(self, ctx, repo):
        node = ctx.node
        if ctx.action not in self.ACTIONS or node is None or Status(node["status"]) not in LOCKED_STATUSES:
            return
        if ctx.action == "edge.upsert" and ctx.existing_edge and \
                ctx.existing_edge.get("signature") == ctx.edge.get("signature"):
            return  # purpose/text refresh only
        if ctx.action == "node.update" and not any(
                k in CONTENT_FIELDS and ctx.fields[k] != node.get(k) for k in ctx.fields):
            return
        if ctx.action in ("task.start", "task.add_node") and self._refinement_exempt(ctx, repo, node):
            return
        require_adr(repo, ctx, [node["id"]], self.name,
                    f"'{node['id']}' is {node['status']}; {ctx.action} needs an accepted ADR")

    @staticmethod
    def _refinement_exempt(ctx, repo, node) -> bool:
        if not ctx.task or ctx.task["kind"] != TaskKind.REFINEMENT.value or node["status"] != Status.TESTED.value:
            return False
        return Verdict.FAIL.value in repo.latest_verdicts(node["id"]).values()


class OwnershipPolicy(Policy):
    """A node inside an active task belongs to that task: other tasks may not edit or claim it.

    Approvers (orchestrator) may edit, but even they cannot start a second task on an owned node.
    """
    name = "OWNERSHIP"
    ACTIONS = ("node.update", "node.delete", "edge.upsert", "edge.delete", "task.start", "task.add_node")

    def check(self, ctx, repo):
        if ctx.action not in self.ACTIONS or ctx.node is None:
            return
        if ctx.action not in ("task.start", "task.add_node") and _is_approver(repo, ctx.actor):
            return
        others = [t for t in repo.active_tasks_for_node(ctx.node["id"]) if t["id"] != ctx.task_id]
        if others:
            raise PolicyViolation(self.name, f"'{ctx.node['id']}' is owned by active task(s) "
                                  f"{[t['id'] for t in others]}",
                                  {"owners": others, "next_step": "Pass --task <your task id> if the node is in "
                                   "your task; otherwise escalate to the orchestrator."})


class ContractPolicy(Policy):
    """Function edges are contracts between parallel agents.

    Contract change = changing/removing an existing CALLS signature, or demanding a
    new function from a callee that someone else owns or that is baselined.
    Edges created inside your own current task are drafts and may change freely.
    """
    name = "CONTRACT_CHANGE"

    def check(self, ctx, repo):
        if ctx.action not in ("edge.upsert", "edge.delete") or (ctx.edge or {}).get("kind") != EdgeKind.CALLS.value:
            return
        e, old, callee = ctx.edge, ctx.existing_edge, ctx.target
        own_draft = bool(old and ctx.task_id and old.get("task_id") == ctx.task_id)
        if ctx.action == "edge.delete":
            if not own_draft:
                self._violation(repo, ctx, callee, e, "removing a function edge that is not your own draft")
            return
        if old:
            if old.get("signature") != e.get("signature") and not own_draft:
                self._violation(repo, ctx, callee, e,
                                f"signature change {old.get('signature')!r} -> {e.get('signature')!r}")
            return
        exposed = [x for x in repo.edges(kind=EdgeKind.CALLS.value, to_id=callee["id"], function_name=e["function_name"])]
        if exposed:
            if any(x.get("signature") != e.get("signature") for x in exposed):
                self._violation(repo, ctx, callee, e, f"'{e['function_name']}' already exists on '{callee['id']}' "
                                f"with signature {exposed[0].get('signature')!r}; reuse it exactly")
            return
        foreign_owner = [t for t in repo.active_tasks_for_node(callee["id"]) if t["id"] != ctx.task_id]
        if Status(callee["status"]) in LOCKED_STATUSES or foreign_owner:
            self._violation(repo, ctx, callee, e, f"new function '{e['function_name']}' demanded from "
                            f"'{callee['id']}' ({callee['status']}, owners {[t['id'] for t in foreign_owner]})")

    def _violation(self, repo, ctx, callee, e, why):
        if _is_approver(repo, ctx.actor) and not ctx.task_id:
            return  # orchestrator re-shaping the contract-first design
        impacted = self.impacted(repo, callee, e["function_name"])
        require_adr(repo, ctx, [callee["id"]], self.name, f"contract change: {why}", {"impacted": impacted})

    @staticmethod
    def impacted(repo, callee, function_name) -> list[dict]:
        out = []
        for x in repo.edges(kind=EdgeKind.CALLS.value, to_id=callee["id"], function_name=function_name):
            out.append({"caller": x["from_id"], "signature": x.get("signature"),
                        "active_tasks": repo.active_tasks_for_node(x["from_id"])})
        out.append({"callee": callee["id"], "active_tasks": repo.active_tasks_for_node(callee["id"])})
        return out


class StatusPolicy(Policy):
    """Lifecycle: PLANNED -> IN_PROGRESS -> COMPLETED -> TESTED -> EVALUATED.

    EVALUATED needs the node to be TESTED, at least one recorded eval result,
    and no eval whose latest verdict is FAIL. Leaving a locked status needs an ADR.
    """
    name = "STATUS"

    def check(self, ctx, repo):
        if ctx.action != "node.status":
            return
        node, new = ctx.node, Status(ctx.fields["status"])
        old = Status(node["status"])
        if new == old:
            return
        if STATUS_ORDER.index(new) < STATUS_ORDER.index(old):
            if old in LOCKED_STATUSES:
                require_adr(repo, ctx, [node["id"]], self.name, f"moving '{node['id']}' back from {old.value}")
            return
        if new is Status.EVALUATED:
            if old is not Status.TESTED:
                raise PolicyViolation(self.name, f"EVALUATED requires TESTED first (node is {old.value})")
            verdicts = repo.latest_verdicts(node["id"])
            if not verdicts:
                raise PolicyViolation(self.name, "EVALUATED requires recorded eval results (cg eval record ...)")
            failing = sorted(k for k, v in verdicts.items() if v == Verdict.FAIL.value)
            if failing:
                raise PolicyViolation(self.name, f"EVALUATED blocked by failing evals {failing}",
                                      {"failing_evals": failing})


DEFAULT_POLICIES: list[Policy] = [DesignLockPolicy(), LockedNodePolicy(), OwnershipPolicy(), ContractPolicy(),
                                  StatusPolicy()]
