"""Domain vocabulary for the code graph: C4 types, layers, lifecycle, edges, errors.

Single place to extend the vocabulary. Adding a node type = one enum member
plus (optionally) a C4 rank entry. Nothing else in the package hard-codes
these values.
"""
from __future__ import annotations

from enum import Enum


class NodeType(str, Enum):
    COMPONENT = "COMPONENT"
    SERVICE_CLASS = "SERVICE_CLASS"
    CLASS = "CLASS"
    INTERFACE = "INTERFACE"
    UTILITY_CLASS = "UTILITY_CLASS"
    CONFIG_CLASS = "CONFIG_CLASS"


# C4 depth: lower rank = higher C4 level. HAS goes from lower rank to higher
# rank; DEPENDS stays within a rank; CALLS connects code-level nodes (rank >= 1).
C4_RANK = {
    NodeType.COMPONENT: 0,
    NodeType.SERVICE_CLASS: 1,
    NodeType.CLASS: 2,
    NodeType.INTERFACE: 2,
    NodeType.UTILITY_CLASS: 2,
    NodeType.CONFIG_CLASS: 2,
}


class Layer(str, Enum):
    PLATFORM = "PLATFORM"
    USECASE = "USECASE"


class Status(str, Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    TESTED = "TESTED"
    EVALUATED = "EVALUATED"


STATUS_ORDER = [s for s in Status]
# Nodes in these statuses are baselined: changing them needs an accepted ADR.
LOCKED_STATUSES = {Status.TESTED, Status.EVALUATED}
# Accept the spellings used in the original spec.
STATUS_ALIASES = {"PLANED": "PLANNED", "PROGRES": "IN_PROGRESS", "PROGRESS": "IN_PROGRESS",
                  "COMPLTED": "COMPLETED", "DONE": "COMPLETED"}


class EdgeKind(str, Enum):
    HAS = "HAS"          # C4 containment, parent -> child
    DEPENDS = "DEPENDS"  # same-level dependency
    CALLS = "CALLS"      # function call, caller -> callee, named by function
    IMPLEMENTS = "IMPLEMENTS"  # class -> INTERFACE it realises (plugin/strategy points)
    USES = "USES"        # code node -> shared type it imports without calling (models, configs)


class AdrStatus(str, Enum):
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class TaskStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


ACTIVE_TASK_STATUSES = {TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED}


class TaskKind(str, Enum):
    FEATURE = "FEATURE"
    REFINEMENT = "REFINEMENT"  # fixes review findings; exempt from ADR on TESTED nodes with open FAILs


class EvalCategory(str, Enum):
    ARCH = "ARCH"
    APP_DESIGN = "APP_DESIGN"
    CODE = "CODE"
    BUSINESS = "BUSINESS"
    SECURITY = "SECURITY"
    PERFORMANCE = "PERFORMANCE"


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WAIVED = "WAIVED"


NODE_FIELDS = ("name", "type", "layer", "status", "business_intent", "extensibility",
               "contract", "code_path", "loc", "complexity", "complexity_note", "owner")
# Fields that describe design/code; editing them on a locked node needs an ADR.
CONTENT_FIELDS = tuple(f for f in NODE_FIELDS if f != "status")


def parse_enum(enum_cls, value, field: str):
    if value is None:
        return None
    raw = str(value).strip().upper().replace("-", "_")
    if enum_cls is Status:
        raw = STATUS_ALIASES.get(raw, raw)
    try:
        return enum_cls(raw)
    except ValueError:
        allowed = ", ".join(m.value for m in enum_cls)
        raise ValidationError(f"invalid {field} '{value}'", {"allowed": allowed}) from None


class GraphError(Exception):
    code = "ERROR"
    exit_code = 1

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message, "details": self.details}


class NotFound(GraphError):
    code = "NOT_FOUND"
    exit_code = 2


class ValidationError(GraphError):
    code = "INVALID"
    exit_code = 2


class PolicyViolation(GraphError):
    """A governance rule blocked the change. The agent must escalate (propose an ADR)."""
    code = "POLICY_VIOLATION"
    exit_code = 3

    def __init__(self, rule: str, message: str, details: dict | None = None):
        super().__init__(message, {"rule": rule, **(details or {})})
        self.rule = rule
