# Coder lessons (least-followed EVALs)

The orchestrator maintains this file from `cg eval report` after each cycle (see `.claude/skills/orchestrate-cycle/reference/maturity-review.md`). Newest first. Each lesson names the EVAL, the recurring mistake, and the concrete fix. Remove a lesson once its EVAL's first-pass rate stays at 0.8 or above for two cycles.

| EVAL | Recurring mistake | Do this instead |
|---|---|---|
| CODE-002 | Hand-counted LOC 15–40% above the measured value (wave 1b) | Run `cg scan-loc --actor <you> --task <T>` (it measures only your task's nodes and records the LOC); never count by hand |
| ARCH-007 | Shared types imported without an edge, so `cg impact` misses the blast radius | `cg edge add USES <me> core.domain_models` (and config_manager.config_models, etc.) for every shared type you import |
| APP-102 | Relying on in-memory bus semantics (cross-topic order, synchronous delivery) | Assume order per topic only and at-least-once delivery (ADR-0002); make handlers idempotent |
| ARCH-006 | CALLS edges recorded at the end, or not at all; signatures drift from code | Run `cg edge add CALLS` the moment you write the call; paste the signature from the code |
| CODE-001 | Tests cover the happy path only | For each `calls_in` function, test normal, boundary and error cases, and name tests after the contract function |
| APP-002 | Extension point claimed but a new variant needs an `if type == ...` in platform code | New variants register through the interface or registry; grep your platform code for type switches |
| APP-006 | `datetime.now()`, `random.random()`, or repository construction inside business logic | Inject a Clock/RNG/port through the constructor; tests pass fakes |
| CODE-003 | Private copies of money rounding or time helpers | Run `cg util find` first; register new shared helpers |

_Seeded with common failure modes; replace them with project evidence as cycles run._
