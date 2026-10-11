# Security review checklist (SECURITY)

Defensive review of the project's own code. Apply each SECURITY EVAL from `cg eval list --category SECURITY`.

## Map the trust boundaries
Entry points in scope: HTTP/admin APIs, feed consumers (Kafka/simulator), file and config loaders, UI inputs. Follow untrusted data along the `calls_out` edges until it is validated or reaches a sink.

## Checks
- **Validation (SEC-001):** type, range, size and format are checked at the boundary. IDs and enums come from allow-lists, and amounts are checked for sign and precision. Validation errors do not leak internals.
- **Secrets and PII (SEC-002):** no credentials in code, config or tests. Secrets come from environment or a vault. Logs carry no secrets, and user/account identifiers are minimised or pseudonymised.
- **Injection (SEC-003):** SQL is parameterised. No `eval`/`exec`, no `pickle`/`yaml.load` of untrusted data, no `shell=True` with untrusted input, no path traversal in file access.
- **Authorisation:** admin operations (create, edit, delete) check the caller's role server-side. Resource ids cannot be enumerated across tenants.
- **Randomness (SEC-004):** outcomes that move money or decide rewards use `secrets`/CSPRNG, or a certified RNG, behind an injectable port. `random` is acceptable only in simulators and tests.
- **Integrity:** quota, balance and ledger updates are atomic (no check-then-act race) and idempotent per event id, so replays cannot apply twice.
- **Dependencies:** new third-party packages are pinned and justified.

Severity guidance: a data-integrity or money flaw is at least MAJOR; injection or an authorisation bypass is BLOCKER.
