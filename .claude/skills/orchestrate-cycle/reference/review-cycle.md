# Review cycle

## When
A batch of tasks is DONE and their nodes are TESTED. Review per batch, not per node, so reviewers see the interactions between nodes.

## Who
| Reviewer agent | Always | Also when |
|---|---|---|
| `arch-reviewer` (ARCH) | ✓ | |
| `app-design-reviewer` (APP_DESIGN) | ✓ | |
| `code-reviewer` (CODE + BUSINESS) | ✓ | |
| `security-reviewer` (SECURITY) | | the nodes touch APIs, feeds, files, auth, persistence, money or RNG |
| `performance-reviewer` (PERFORMANCE) | | the nodes are on a per-event/per-request path or hold growing state |

Launch them in one message so they run in parallel. Brief each with: project root, task ids, node ids, its category, and any project-specific focus (for example "BIZ-101 budget cap under concurrency").

## Collect
Each reviewer records verdicts in the graph and returns a verdict table, findings with refinement proposals, and EVAL gaps.
- Conflicting proposals between reviewers: you decide. If an EVAL does not apply, record WAIVED with the reason yourself.
- A refinement that needs a contract change goes through the escalation protocol.

## Refine
One `REFINEMENT` task per coherent group of findings (no shared nodes across parallel tasks):
`cg task new --kind REFINEMENT --title "Fix <EVAL ids> on <node>" --desc "<findings + expected fix>" --nodes <ids> --agent coder-N`.
REFINEMENT tasks on TESTED nodes with open FAILs are ADR-exempt. Prefer the original coder, since they already have the context.

## Re-review and gate
- Re-run only the reviewers whose EVALs failed, scoped to the refined nodes.
- Gate: when `latest_verdicts` has no FAIL, run `cg node status <id> EVALUATED --actor orchestrator` (the tool enforces the gate).
- A component is EVALUATED when all its children are.
