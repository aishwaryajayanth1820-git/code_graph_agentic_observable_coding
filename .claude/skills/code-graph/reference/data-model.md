# Code graph data model and governance

## Nodes (C4 objects; functions are edges, not nodes)

| # | Field | Meaning | Who fills it |
|---|---|---|---|
| 1 | `id` | Unique, stable id. Convention: `<component>` or `<component>.<snake_class>` | orchestrator |
| 2 | `name` | Unique component/class name (the class name in code) | orchestrator |
| 3 | `business_intent` | The business logic this node holds | orchestrator, refined by coder |
| 4 | `extensibility` | Anticipated extension and the adaptive pattern (e.g. "new channel = new plugin; Strategy + registry") | orchestrator |
| 5 | `type` | `COMPONENT`, `SERVICE_CLASS`, `CLASS`, `INTERFACE`, `UTILITY_CLASS`, `CONFIG_CLASS` | orchestrator |
| 6 | `layer` | `PLATFORM` (reusable, use-case agnostic) or `USECASE` (built on platform extension points) | orchestrator |
| 7 | `status` | `PLANNED` → `IN_PROGRESS` → `COMPLETED` → `TESTED` → `EVALUATED` | coder up to TESTED; orchestrator sets EVALUATED |
| 8 | `change_count` | +1 each time a task that includes the node starts (once per task, not per edit) | tool |
| 9 | ADRs | ADRs linked to the node (UI shows them; click for detail) | tool / orchestrator |
| 10 | `loc`, `complexity`, `complexity_note` | Lines of code (or `cg scan-loc`) and a 1–10 self-assessment | coder |
| 11 | `code_path` | Path relative to the project root: `src/pkg/mod.py::Class`, a file, or a directory (components) | orchestrator plans it, coder confirms |
| 12 | `fan_out` / `fan_in` | Number of CALLS edges out of / into the node (derived) | tool, from the coder's edges |
| – | `contract` | Human summary of the public methods (the CALLS edges are the enforced contract) | orchestrator / coder |
| – | `owner` | Optional long-lived owner | orchestrator |

Legacy spellings from the spec (`PLANED`, `PROGRES`, `COMPLTED`) are accepted.

### Complexity self-assessment (1–10)
1–2 data holder or thin facade · 3–4 straightforward logic · 5–6 several branches or some state · 7 upper bound (`max_complexity`) · 8–10 must be split (propose an ADR).

## Edges

| Kind | From → To | Rule |
|---|---|---|
| `HAS` | higher C4 level → lower (COMPONENT → SERVICE_CLASS → CLASS…) | one parent per node |
| `DEPENDS` | node → node of the **same** C4 level | declare every component dependency |
| `CALLS` | caller → callee (both code-level, not COMPONENT) | named by function; needs `signature` and `purpose`; one edge per (caller, callee, function) |
| `IMPLEMENTS` | code-level node → INTERFACE | plugin/strategy realisation |
| `USES` | code-level node → code-level node | a shared type imported without a call (models, config classes); counted in impact, coupling, cycles and G01/G03 |

## Governance policies (blocking; exit code 3)

| Rule | Triggers | Passes when |
|---|---|---|
| `DESIGN_LOCK` | adding or removing a node after `cg design lock` | `--adr` names an ACCEPTED ADR (it is linked to the new node automatically) |
| `LOCKED_NODE` | editing, deleting, re-tasking, or changing the edges of a TESTED/EVALUATED node | ACCEPTED ADR linked to the node. Exception: a `REFINEMENT` task on a TESTED node that has a failing EVAL |
| `OWNERSHIP` | touching a node that belongs to another active (IN_PROGRESS/BLOCKED) task, or starting a second task on it | you pass the owning `--task`. Approvers may edit, but cannot double-assign |
| `CONTRACT_CHANGE` | CALLS signature change or removal (unless the edge was created in *your* current task), a signature that differs from the callee's existing function, or a new function demanded from a callee that is TESTED/EVALUATED or owned by another task | ACCEPTED ADR linked to the callee. `details.impacted` lists the callers and active tasks to notify |
| `STATUS` | EVALUATED without TESTED first, without any recorded EVAL, or with a failing latest verdict; moving back out of TESTED/EVALUATED | fix the precondition / ADR |
| `APPROVER` | ADR accept/reject/link, design lock, config set by a non-approver | actor in `approvers` (default `orchestrator,human`) |

Policies live in `code_graph/codegraph/rules.py`. Each one is a small class with `check(ctx, repo)`, so a project can add or replace them.

## Deterministic checks (`cg check`)

| Rule | Severity | Check |
|---|---|---|
| G01 | ERROR | PLATFORM node CALLS/DEPENDS/IMPLEMENTS a USECASE node |
| G02 | ERROR | Component dependency cycle (DEPENDS plus cross-component CALLS) |
| G03 | WARN | Cross-component CALLS without a declared component DEPENDS edge |
| G04 | WARN | Cross-component CALLS to a concrete CLASS (depend on INTERFACE/SERVICE_CLASS; UTILITY_CLASS and CONFIG_CLASS are shareable) |
| G05 | WARN | Code-level node without a parent |
| G06 | WARN/INFO | COMPLETED+ node missing code_path / loc / complexity |
| G07 | WARN | complexity > `max_complexity` (7) |
| G08 | WARN | more than `max_fan_out` (7) distinct collaborators called (fan-out itself counts function edges) |
| G09 | WARN | loc > `max_loc` (300) |
| G11 | WARN | COMPLETED+ INTERFACE with no IMPLEMENTS edge |
| G13 | WARN | CALLS to an INTERFACE function that its contract does not declare (stale edge after a contract change, or an undeclared method) |

## Metrics (`cg metrics`)
- Per component: status counts, LOC, average/max complexity, change count, fan-in/out, afferent (Ca) and efferent (Ce) coupling, instability `I = Ce/(Ca+Ce)`, abstractness `A` (interfaces ÷ classes), distance from the main sequence `D = |A+I-1|`, ADR count.
- `platform_maturity`:
  - `usecase_tasks_touching_platform_pct`: share of use-case tasks that also had to change platform nodes. Falling = the platform absorbs use cases without edits.
  - `platform_instability_avg`: should trend towards 0.
  - `platform_change_per_node`, `platform_evaluated_pct`, `platform_adrs`.
  - `dependency_direction_violations`: must be 0.

## EVAL adherence (`cg eval report`)
`first_pass_rate` = the share of (node, EVAL) pairs whose **first** verdict was PASS, meaning the coder followed the EVAL without being told. `least_followed` ranks the weakest EVALs, and `never_checked` lists EVALs no reviewer has used.
