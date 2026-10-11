# Coder playbook

Goal: deliver your task's nodes so completely that the platform matures and later use cases only add code on top. Rewrites cost the company tokens and risk. Plan before you type.

`cg` below means `python code_graph/cg.py`, always with `--actor <you> --task <T>`.

## 1. Orient (no code yet)
1. `cg task get <T>`: read the business context and acceptance criteria. Number them for yourself.
2. `cg task start <T>`. If it exits with code 3, go to §6.
3. For each node: `cg node get <id> --brief`. Read `business_intent`, `extensibility`, `contract`, `calls_in` (what you must provide), `calls_out` (what you may use), and `implements`.
4. Read the existing code at the code paths of the nodes you call. Their CALLS signatures are fixed.
5. `cg impact <id>` for any node that already has code: know who depends on you before you change anything.

## 2. Design inside your nodes
- **One node = one class** at its `code_path` (`file.py::ClassName`). No extra public classes. A private helper class used only here is fine.
- **Depend on abstractions across components.** Import other components' INTERFACE/SERVICE_CLASS only, never their internals.
- **Platform stays use-case agnostic.** No channel-, customer- or variant-specific branches in PLATFORM nodes. Variation goes behind the interface named in `extensibility`.
- **Open/closed at the declared extension point.** Build it so the next anticipated use case needs only a new class or plugin plus registration, then check that claim against your code.
- **No speculative generality.** Add no abstractions the graph does not declare.
- **Inject collaborators** (ports, config, clock, RNG) through constructors. No globals, no hidden I/O.
- **Configuration is data:** read limits and amounts from CONFIG_CLASS objects.
- **Small and flat:** complexity ≤ 7 per node. If it won't fit, escalate a split (ADR).

## 3. Implement and record contracts as you go
- Every call from your class into another class in the graph → `cg edge add CALLS <me> <callee> --fn <f> --sig "<exact signature>" --purpose "<why>"`. Record it when you write the call, not at the end.
- For a signature that already exists in the graph, copy it character for character.
- Your class realises an interface → `cg edge add IMPLEMENTS <me> <interface>`.
- You import a shared type from another node (e.g. `core.domain_models`, `config_manager.config_models`) → `cg edge add USES <me> <that node>`.
- Helpers: `cg util find <words>`. Reuse any match. If you write a helper other nodes could use, put it in the utility module and run `cg util add <name> --purpose --sig --module`.

## 4. Test
- Unit tests for every function other nodes call (your `calls_in`), covering normal, boundary and error cases, plus the business invariants in your acceptance criteria.
- Use fakes for ports. No network or real clock. Keep tests deterministic, with the RNG and clock injected.
- Run the tests and keep the command and result for your report.

## 5. Record and finish
```bash
cg node update <id> --path src/x/y.py::Class --loc <n> --complexity <1-10> --complexity-note "<why>" --actor <me> --task <T>
cg node status <id> COMPLETED --actor <me> --task <T>
cg node status <id> TESTED    --actor <me> --task <T>     # only after its tests pass
cg task done <T> --summary "<what was built, key decisions>" --actor <me>
```
Complexity rubric: 1–2 data/facade · 3–4 straightforward · 5–6 branches/state · 7 upper bound · 8–10 must split.
(`cg scan-loc` recounts LOC from code paths when needed.)

## 6. Escalate. Never work around the tool
When you hit exit code 3, need a function on a node you don't own, need to change a signature someone calls, need a new class after design lock, or need to modify a TESTED/EVALUATED node:
```bash
cg adr propose --title "<change>" --context "<why the current contract fails>" --decision "<proposed change>" \
  --consequences "<who is impacted, migration>" --nodes <affected ids> --actor <me>
cg task block <T> --reason "<ADR id>: <one line>" --actor <me>
```
Then stop and return BLOCKED with the ADR id, `details.impacted` from the violation, and the alternatives you considered. Keep any work already done; do not revert it.

## 6b. Scratch files
Temporary scripts go in `<scratchpad>/<your agent name>/`, never in the repository, and never run another agent's files.

## 7. Report to the orchestrator
```text
Task T-000N: DONE | BLOCKED
Nodes: <id> → TESTED, loc 84, complexity 3 (<note>)
Edges: +CALLS a→b.fn(sig) · +IMPLEMENTS c→i
Utilities: reused render_template · added parse_period
Tests: <command> → <n passed>
ADR: <id> (blocked on …; impacted: coder-3/T-0004)
Concerns: <design smells you saw but did not fix>
```
