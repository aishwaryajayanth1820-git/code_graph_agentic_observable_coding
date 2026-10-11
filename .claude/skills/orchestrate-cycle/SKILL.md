---
name: orchestrate-cycle
description: Orchestrator skill. Runs the code → review → refine cycle over a locked code-graph design - slices ready nodes into parallel-safe tasks, dispatches coder agents with task briefs, resolves contract-change escalations through ADRs, runs the reviewer agents, gates EVALUATED, and measures EVAL adherence and platform maturity to improve prompts. Use once the C4 design is locked and until the project is complete.
---

# Orchestrate the build cycle

Tool: `python <project>/code_graph/cg.py ... --actor orchestrator`. Agents: `coder`, `arch-reviewer`, `app-design-reviewer`, `code-reviewer`, `security-reviewer`, `performance-reviewer`.

## One cycle
1. **Slice.** From `cg node list --status PLANNED`, pick nodes whose dependencies are done: platform and interfaces before the use cases that plug into them. Group them into tasks with **no shared nodes**, so they are safe to run in parallel.
2. **Create and dispatch.** For each task, run `cg task new --title --desc --nodes --agent coder-N`, then launch a `coder` agent with a brief built from [reference/task-brief-template.md](reference/task-brief-template.md). Launch parallel coders in one message.
3. **Escalations.** A coder that returns BLOCKED with an ADR id goes through [reference/escalation-protocol.md](reference/escalation-protocol.md). Accepting an ADR means notifying every agent in `impacted` before you resume anyone.
4. **Review.** When a batch's nodes are TESTED, run the reviewers in parallel, as described in [reference/review-cycle.md](reference/review-cycle.md).
5. **Refine or gate.** FAIL verdicts become `REFINEMENT` tasks for coders; re-review only the failed EVALs. When every latest verdict is PASS or WAIVED, run `cg node status <id> EVALUATED`.
6. **Measure and evolve.** After each cycle, run [reference/maturity-review.md](reference/maturity-review.md): `cg metrics`, `cg eval report`, `cg check`. Append to `<project>/design/evolution_log.md`, and move the guidance behind the least-followed EVALs into `.claude/playbooks/coder-lessons.md`.

Repeat until every node is EVALUATED. Report progress to the user with the UI link (`#view=metrics`).

## Rules for yourself
- The graph is the only status board. Never track progress anywhere it cannot see.
- Accept an ADR yourself only when it stays inside the approved design. Ask the user when it changes a platform contract or the component structure.
- Keep coders on their nodes. A cross-cutting fix is a new task, not scope creep.
