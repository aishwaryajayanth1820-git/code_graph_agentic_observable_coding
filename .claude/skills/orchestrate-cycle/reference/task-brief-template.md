# Coder task brief template

Fill this in from `cg task get <T>`, `cg node get <id>` and `cg impact <id>`, then pass it as the `coder` agent's prompt. Keep it factual. The agent reads its playbook for the *how*.

**Store the acceptance criteria in the task record** (`cg task new --desc "<numbered criteria>"`), not only in the agent prompt. Reviewers read `cg task get`, and a description that says "see the brief" forces them to reconstruct the criteria (found in the cycle-1 code review).

```text
Project root: <abs path>        Tool: python code_graph/cg.py
Your agent name: <coder-N>      Task: <T-000N> (<FEATURE|REFINEMENT>)
Always pass: --actor <coder-N> --task <T-000N>

## Nodes you own in this task
- <id> (<TYPE>, <LAYER>) — <business_intent>
  extensibility: <extensibility>   code_path: <code_path>

## Business context and acceptance criteria
<The requirement slice in business terms, why it matters, and numbered, testable criteria with concrete numbers.>

## Contracts
Provide (callers depend on these; do not change them):  <callee.fn signature — caller>
Consume (call exactly as written):                      <caller -> callee.fn signature>
Planned but missing? Stop and escalate. Do not invent a cross-node function.

## Parallel work: do not touch
<T-000M (coder-M): nodes ...>

## Anticipated extensions this code must accept without rewrite
<For example: "SMS and push channels will be added as plugins next.">

## EVALs that will be applied
<ids + titles for ARCH/APP/CODE/BIZ (+SEC/PERF if relevant)>
Extra attention (least followed so far): <ids from cg eval report>

## For REFINEMENT tasks: findings to fix
<eval id, node, reviewer notes, expected fix>

## Definition of done
Code + passing unit tests; CALLS/IMPLEMENTS edges recorded; node path/loc/complexity set; nodes TESTED; `cg task done` with summary; report returned.
```
