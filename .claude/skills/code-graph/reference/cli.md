# cg command reference

`python code_graph/cg.py [--db PATH] [--actor NAME] [--task ID] [--adr ID] [--pretty] <command> ...`

Global options work before or after the subcommand. They fall back to the env vars `CG_DB`, `CG_ACTOR`, `CG_TASK` and `CG_ADR`. The default database is `code_graph/code_graph.db`, next to `cg.py`. Output is JSON on stdout; errors are JSON on stderr (`{"error", "message", "details"}`).

| Exit code | Meaning | What to do |
|---|---|---|
| 0 | ok | |
| 1 | unexpected error (I/O, bad JSON file) | report it |
| 2 | `INVALID` / `NOT_FOUND` | fix the input |
| 3 | `POLICY_VIOLATION` | stop and escalate (see `details.rule`, `details.next_step`, `details.impacted`) |

Nodes can be referenced by id or by name (case-insensitive).

## Project

```bash
cg install <project_dir> [--name N] [--with-claude] [--force]   # clone the tool into <project_dir>/code_graph and init its db
cg init --project <name>
cg serve [--host 127.0.0.1] [--port 8770]                        # UI at /ui/, OpenAPI at /docs
cg config show
cg config set <key> <value> --actor orchestrator                 # max_complexity | max_fan_out | max_loc | approvers | project_root
cg design lock|unlock|status --actor orchestrator                # after lock, new/removed nodes need an ADR
cg import <seed.json> --actor orchestrator                       # idempotent upsert of nodes/edges/utilities/evals
cg export [file.json]
```

## Nodes

```bash
cg node add <id> --name <ClassName> --type CLASS [--layer PLATFORM|USECASE] [--parent <id>] \
   [--intent "..."] [--ext "anticipated extension + pattern"] [--contract "public methods"] \
   [--path src/pkg/mod.py::ClassName] [--loc N] [--complexity 1-10] [--complexity-note "..."] [--owner NAME]
cg node update <ref> [same field flags] [--status S]
cg node status <ref> PLANNED|IN_PROGRESS|COMPLETED|TESTED|EVALUATED
cg node get <ref> [--brief]            # fields + fan-in/out edges, children, tasks, ADRs, verdicts, history
cg node list [--type T] [--layer L] [--status S] [--parent <component>] [--q "words"]
cg node rm <ref>
```

`--layer` is inherited from `--parent` when omitted. `fan_in`/`fan_out` are derived from CALLS edges, never typed in.

## Edges

```bash
cg edge add HAS <parent> <child>                       # containment (usually created by node add --parent)
cg edge add DEPENDS <component> <component>            # same C4 level
cg edge add CALLS <caller> <callee> --fn <function> --sig "<signature>" --purpose "<why the call is made>"
cg edge add IMPLEMENTS <class> <interface>
cg edge add USES <importer> <shared type>              # type dependency without a call (models, configs)
cg edge rm <KIND> <from> <to> [--fn <function>]
cg edge list [--node <ref>] [--kind K]
```

Running `edge add` again on an existing edge updates it. The response has `created`, `changed` and `contract_changed` flags.

## Tasks

```bash
cg task new --title "..." --desc "business context + acceptance criteria" --nodes a,b [--kind FEATURE|REFINEMENT] [--agent coder-1] [--adr ADR-0003] --actor orchestrator
cg task start <T> --actor coder-1 [--adr ADR-0003]    # +1 change_count per node (once per task); nodes -> IN_PROGRESS
cg task add-node <T> <ref> --actor coder-1            # extend scope (same policies as start)
cg task done <T> --summary "..." --actor coder-1      # warns if nodes are still PLANNED/IN_PROGRESS
cg task block <T> --reason "ADR-0004: needs get_templates on ConfigLibrary" --actor coder-1
cg task cancel <T> --reason "..."
cg task get <T>
cg task list [--status S] [--agent A] [--node <ref>]
```

## ADRs

```bash
cg adr propose --title "..." --context "why" --decision "what" [--consequences "impact"] --nodes a,b --actor coder-1
cg adr accept|reject|supersede <ADR> [--note "..."] --actor orchestrator     # approvers only (config: approvers)
cg adr link <ADR> a,b --actor orchestrator
cg adr get <ADR>
cg adr list [--status S] [--node <ref>]
```

## Utilities

```bash
cg util find render template         # {"matches": [...all words...], "related": [...any word...], "advice": ...}
cg util add <name> --purpose "..." [--sig "<signature>"] [--module src/common/x.py] [--node <utility class id>] --actor coder-1
cg util list
```

## EVALs

```bash
cg eval add ARCH-007 --category ARCH --title "..." --rule "testable statement" [--method "how to check"] [--severity BLOCKER|MAJOR|MINOR]
cg eval import <evals.json>                         # a JSON list, or {"evals": [...]}
cg eval list [--category ARCH|APP_DESIGN|CODE|BUSINESS|SECURITY|PERFORMANCE]
cg eval record <EVAL> --node <ref> --verdict PASS|FAIL|WAIVED [--notes "..."] [--task <T>] [--coder <agent>] --actor arch-reviewer
cg eval report [--category C]                       # first-pass rate per EVAL and per coder, least_followed, never_checked
```

A FAIL verdict requires `--notes`. `--coder` defaults to the agent of the node's latest task.

## Analysis

```bash
cg impact <ref> [--depth 3]    # reverse CALLS/DEPENDS/IMPLEMENTS: impacted nodes, contracts, locked nodes, agents_to_notify
cg metrics                     # progress, per-component coupling/instability/abstractness, platform_maturity
cg check                       # deterministic ArchUnit-style rules G01..G11 over the graph (passed = no ERROR)
cg scan-loc [--task <T>] [--dry-run]  # recount LOC from code_path (Python class spans via ast); --task limits to that task's nodes; --dry-run writes nothing
cg audit [--target <ref>] [--limit 50]
```

## Worked example: contract change during parallel work

```bash
$ cg edge add CALLS email_channel.email_sender config_manager.config_library --fn get_templates \
    --sig "get_templates(channel_id: str) -> list[Template]" --purpose "message templates" --actor coder-2 --task T-0002
# exit 3: CONTRACT_CHANGE, new function demanded from EVALUATED config_library; details.impacted lists owners
$ cg adr propose --title "Expose templates on ConfigLibrary" --context "..." --decision "..." \
    --nodes config_manager.config_library --actor coder-2
$ cg task block T-0002 --reason "ADR-0001 pending" --actor coder-2
# -> return to the orchestrator with ADR-0001. After acceptance, retry the edge add with --adr ADR-0001.
```
