---
name: code-graph
description: Read and record the project's code dependency graph with the `cg` CLI - C4 nodes, function contracts (CALLS edges), tasks, ADRs, the utility registry and EVAL verdicts. Use whenever you plan, implement or review code in a project that has a code_graph/ folder, before writing any helper/utility, before adding or changing a function another class calls, and whenever a cg command exits with code 3.
---

# Code graph

The graph is the project ledger: C4 nodes (COMPONENT → SERVICE_CLASS → CLASS / INTERFACE / UTILITY_CLASS / CONFIG_CLASS), the function contracts between them, who is working on what, the ADRs behind changes, and review verdicts. Humans watch it live in the UI. Your job is to keep it true.

## Run it
From the project root: `python code_graph/cg.py <command> ...` (prints JSON).
Shell state does not persist between tool calls, so pass identity on **every** mutating command:
`--actor <your agent name> --task <task id>` (add `--adr <id>` when an ADR authorises the change).

## Exit codes
- `0` ok · `2` bad input or not found: fix the command and retry.
- `3` **POLICY_VIOLATION: stop.** Do not work around it. Follow `details.next_step` (usually: propose an ADR), then escalate to the orchestrator with the ADR id and `details.impacted`.

## Coder loop
1. `cg task get <T>` → `cg task start <T> --actor <me>`
2. For each node in the task: `cg node get <id> --brief` (intent, extensibility, contract, calls in/out).
3. Before writing a helper: `cg util find <keywords>`. Reuse any match. A new shared helper: `cg util add`.
4. For every call you implement between classes: `cg edge add CALLS <from> <to> --fn <name> --sig "<exact signature>" --purpose "<why>"`. For an existing contract, reuse its signature exactly. For a class realising an interface: `cg edge add IMPLEMENTS <class> <interface>`. For every shared type you import from another node without calling it (domain models, config classes): `cg edge add USES <me> <type node>`, so its blast radius is visible.
5. `cg node update <id> --path <file>::<Class> --loc <n> --complexity <1-10> --complexity-note "<why>"`, then `cg node status <id> COMPLETED`. Once its unit tests pass: `TESTED`.
6. `cg task done <T> --summary "<what changed>"`

## Reviewer loop
`cg node get <id>` · `cg check` · `cg impact <id>` → `cg eval record <EVAL> --node <id> --verdict PASS|FAIL|WAIVED --notes "<evidence and fix>" --actor <me>`

## Never
- Change a node outside your task, a signature another class depends on, or the design after lock, without an ACCEPTED ADR. The tool enforces this and exits with code 3.
- Set a node to EVALUATED (orchestrator only; the tool blocks it while any EVAL is failing).
- Edit `code_graph.db` directly.

## More
- Every command, with examples: [reference/cli.md](reference/cli.md)
- Node fields, lifecycle, edge rules, governance policies, checks and metrics: [reference/data-model.md](reference/data-model.md)
- Seed JSON for bulk design import (orchestrator): [reference/seed-format.md](reference/seed-format.md)
- UI for humans: `cg serve --port 8770` → `http://127.0.0.1:8770/ui/` (deep link `#node=<id>`)
