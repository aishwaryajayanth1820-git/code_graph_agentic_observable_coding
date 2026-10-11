# Application design review checklist (APP_DESIGN)

Apply each APP_DESIGN EVAL from `cg eval list --category APP_DESIGN`. The target is extensible without over-complicated: judge both directions.

## Per class (SOLID)
- **S (APP-001):** Can the class's job be stated in one sentence matching `business_intent`? Look for multiple reasons to change: I/O mixed with rules, or formatting mixed with calculation.
- **O (APP-002):** Take the `extensibility` field literally. Write down the files the next anticipated use case would add or edit. Any edit to this class, or a type switch or `if kind ==` chain, fails the claim.
- **L:** Implementations honour the interface: same pre/postconditions, no `NotImplementedError` stubs, no narrowed inputs.
- **I:** Interfaces are small and client-specific. Flag methods a client never calls.
- **D (APP-006):** Collaborators come in through constructors or factories. Business logic contains no `datetime.now()`, `random`, environment reads or repository construction.

## Contracts (APP-003)
- Public signatures are fully typed, and errors are part of the contract (documented exceptions or result types).
- No leaked implementation types: DB rows, ORM objects, HTTP request objects or framework types crossing the boundary.
- The CALLS edge signatures in the graph equal the code.

## Configuration (APP-004)
Business numbers (caps, frequencies, amounts, thresholds) live in CONFIG_CLASS objects and are validated when loaded.

## Over-engineering (APP-005)
Every interface, base class, factory or registry has a second implementation or a declared extension point. Otherwise it fails, and your proposal is to inline it.

## Report extras
For each extension point, give a one-line answer to "a new <use case> needs: <files>". The orchestrator uses this for the platform maturity review.
