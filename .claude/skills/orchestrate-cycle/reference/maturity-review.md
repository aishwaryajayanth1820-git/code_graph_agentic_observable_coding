# Maturity review and evolution loop

Run after every cycle: `cg metrics`, `cg eval report`, `cg check`. These numbers replace free-text reasoning about quality.

## Signals → actions
| Signal (cg metrics) | Healthy | If not |
|---|---|---|
| `platform_maturity.usecase_tasks_touching_platform_pct` | falls cycle over cycle; < 20% once the platform is EVALUATED | The platform is missing an extension point. Create a design task to add it; do not keep patching |
| `platform_instability_avg` | ≤ 0.3 | The platform depends outward. Invert with a port/interface |
| `dependency_direction_violations`, `cg check` ERRORs | 0 | Blocker for the next cycle |
| component `distance_main_sequence` | ≤ 0.5 | ≈1 with I≈0,A≈0 means concrete and depended upon ("zone of pain"). Extract interfaces |
| node `change_count` × `fan_in` hotspots | low | A volatile core. Stabilise the contract (ADR) before more use cases land |
| complexity > 7, fan-out > 7, loc > 300 | none | A split task (ADR) |
| ADRs per cycle for the same component | ≤ 1 | Under-designed contract. Redesign the component's contracts |

Change radius: for the top 3 hotspots, run `cg impact <id>`. Before accepting more change there, turn large blast radii into design suggestions for the coders (an interface extraction or an adapter).

## EVAL learning loop
1. `cg eval report` → `least_followed` (first_pass_rate < 0.7) and `coders`.
2. For each weak EVAL, write one concrete, example-backed lesson at the top of `.claude/playbooks/coder-lessons.md`, and list the EVAL under "Extra attention" in the next briefs.
3. Next cycle, compare the first_pass_rate. If it is still low after 2 cycles, change the mechanism: add a `cg check` rule, a test template or a script, rather than more prose.
4. `never_checked` EVALs: fix the reviewer briefs.
5. Reviewer-proposed EVAL gaps: add the good ones (`cg eval add`, id 100+).

## `<project>/design/evolution_log.md`
```markdown
| Cycle | Date | Tasks | Evaluated % | UC→platform % | Platform I | Least followed (rate) | ADRs | Prompt/skill changes made | Effect next cycle |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-10-01 | T-0001..T-0006 | 35 | 0 | 0.20 | CODE-001 (0.4) | 1 | coder-lessons: test per CALLS-in fn | CODE-001 → 0.8 |
```
