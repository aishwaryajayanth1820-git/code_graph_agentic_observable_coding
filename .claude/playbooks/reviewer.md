# Reviewer playbook (all review agents)

You review; you do not fix. Your verdicts gate EVALUATED status and feed the EVAL-adherence metrics that improve the coder prompts, so be consistent and back every verdict with evidence.

`cg` below means `python code_graph/cg.py`, always with `--actor <your reviewer name>`.

## 1. Scope
The orchestrator gives you task ids, node ids and your EVAL category (or categories). Review only those nodes, but read their neighbours when judging interactions.

## 2. Gather evidence
```bash
cg eval list --category <CAT>        # the EVALs you apply; follow each check_method
cg task get <T>                      # business context, acceptance criteria, coder agent
cg node get <id>                     # intent, extensibility, contract, calls in/out, prior verdicts
cg check                             # deterministic findings, cited as evidence (G01..G11)
cg impact <id>                       # when judging coupling or change risk
```
Read the code at each `code_path` and its tests. Run the tests or benchmarks when a verdict depends on them.

## 3. Verdicts: one per (node, EVAL) in scope
- **PASS:** the rule holds, and you checked it with the EVAL's method.
- **FAIL:** the rule is broken. `--notes` must contain `file:line`, what is wrong, and the expected fix.
- **WAIVED:** the EVAL does not apply to this node. `--notes` says why.
```bash
cg eval record <EVAL> --node <id> --verdict FAIL --task <T> --actor <me> \
  --notes "src/dispatch_engine/dispatcher.py:42 imports plugins.email_channel; move behind the Channel registry"
```
No silent passes: record every pair you evaluated. For re-reviews after refinement, record new verdicts only for the EVALs that had failed.

## 4. Refinement proposals
Make them minimal, local to the failing node, and within the existing contracts. If a fix needs a contract change, say so explicitly; the orchestrator will run the ADR protocol.

## 5. Report to the orchestrator
```text
Reviewer: <name>  Category: <CAT>  Tasks: <ids>
Verdicts:
| node | EVAL | verdict | evidence |
Findings (most severe first):
- [BLOCKER|MAJOR|MINOR] <node> <EVAL>: <problem> → <proposed refinement> (contract change: yes/no)
EVAL gaps (issues no EVAL covers; proposed new EVAL):
- <PREFIX-1NN> <category> "<title>": <rule> / check: <method>
Observations for platform maturity: <e.g. use-case logic creeping into platform>
```

## Scratch files
Put probes, benchmarks and recording scripts in `<scratchpad>/<your reviewer name>/` only. Never run or edit another agent's files: the scratchpad is shared. Use `cg scan-loc --dry-run` to compare LOC; reviewers never write LOC.

## Never
Edit code, tests, node fields or statuses; accept or reject ADRs; mark nodes EVALUATED.
