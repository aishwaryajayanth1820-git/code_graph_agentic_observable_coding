# Code and business-logic review checklist (CODE, BUSINESS)

Apply each CODE and BUSINESS EVAL from `cg eval list --category CODE` and `--category BUSINESS`.

## Business correctness (BIZ-001, BIZ-002): review this first
1. From `cg task get <T>`, list each acceptance criterion and each invariant the requirement states for these nodes (caps, eligibility, frequency, durability, rounding).
2. For each one, find the enforcing code (file:line) and the test that proves it. A criterion with no test fails.
3. Probe the edges: zero and negative amounts, exact boundary values (amount == threshold), empty input, duplicates, time-window boundaries, and concurrent events for anything with a budget.
4. Numbers: money in Decimal or integer minor units; rounding as specified; no float accumulation.

## Tests (CODE-001)
- Every function in `calls_in` has tests for normal, boundary and error cases.
- Tests are deterministic (injected clock and RNG), isolated (fake ports) and assert behaviour rather than implementation.
- Run them: the test command and result go in your notes.

## Code quality (CODE-002..004)
- `cg scan-loc`: compare with the recorded loc (±10%). Check the complexity self-assessment against the rubric, and `cg check` G07/G09.
- Helpers: run `cg util find <words>` for each helper in the diff. Duplicates fail CODE-003, and so do shared helpers that were not registered.
- Error handling: no bare or silent excepts; boundary failures carry context. Nothing is swallowed in loops.
- Readability: intention-revealing names, no dead code, no commented-out blocks, no TODOs without a task.
