---
name: c4-design
description: Orchestrator skill. Turns an approved implementation plan into a contract-first C4 design in the code graph - components, service classes, classes, interfaces, config and utility classes with HAS/DEPENDS/IMPLEMENTS/CALLS edges - plus the project's EVAL catalog, then locks the design. Use right after the user approves the project plan, or when an accepted ADR adds components or classes.
---

# C4 design → code graph

Prerequisite: the user approved the implementation plan. This skill turns that plan into nodes and contracts that coder agents can build in parallel without rewrites.

## Steps
1. **Set up the graph** (once per project): `python code_graph_tool/cg.py install <project_dir>` (workspace copy). After that, always use `<project_dir>/code_graph/cg.py`.
2. **Decompose**, following [reference/decomposition-guide.md](reference/decomposition-guide.md):
   - Write `<project>/design/c4_design.md` (for humans; template in the guide).
   - Write `<project>/design/c4_seed.json` (for the graph; format in `.claude/skills/code-graph/reference/seed-format.md`).
3. **Contract first.** Before any code exists, every cross-class call has a CALLS edge with an exact signature and purpose, and every extension point is an INTERFACE with IMPLEMENTS edges for the planned implementations.
4. **Import and verify:** `cg import design/c4_seed.json --actor orchestrator`, then `cg check`. The design must have zero ERRORs; resolve G03/G04 WARNs unless they are deliberate.
5. **EVALs:** `cg eval import .claude/skills/c4-design/reference/baseline-evals.json`, then add project-specific EVALs using [reference/eval-authoring.md](reference/eval-authoring.md): business invariants, the extensibility claims, and the non-functional requirements.
6. **Review with the user** in the UI (`cg serve`). Get approval, then run `cg design lock --actor orchestrator`.
7. Hand over to the `orchestrate-cycle` skill.

## Design bar
- Platform first: reusable PLATFORM components expose extension points, and USECASE components only plug into them. PLATFORM never depends on USECASE.
- Extensible without over-engineering: add an abstraction only at an extension point the requirement anticipates.
- Small nodes: aim for one responsibility per class and complexity ≤ 7.
