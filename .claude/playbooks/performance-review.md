# Performance review checklist (PERFORMANCE)

Apply each PERFORMANCE EVAL from `cg eval list --category PERFORMANCE`. Base verdicts on evidence: call-chain reading, then a micro-benchmark if in doubt.

## Map the hot path
Start at the per-event entry point (for example the feed consumer's per-event handler) and walk `calls_out` edges with `cg node get`. Write the chain down, because every hop is a place for per-event cost.

## Checks
- **Per-event cost (PERF-001):** no blocking I/O, DB query or network call per event unless it is designed and cached. No scans over all users, tenants or history per event. Prefer O(1) dict lookups, with no N+1 loops over repositories.
- **Memory (PERF-002):** per-user or per-event collections are bounded (size, TTL or rolling windows). Histories used for probability adjustment are aggregated, not stored raw.
- **Caching and batching (PERF-003):** config and eligibility lookups are cached with an explicit invalidation (for example a config version). Writes are batched where latency allows.
- **Varying traffic:** pacing and probability logic stays correct and cheap under bursts, and there is no per-event recomputation of the historical baseline (recompute on schedule).
- **Concurrency:** no global locks on the hot path. Shared counters (quotas, limits) use atomic operations.

## Evidence
When a verdict depends on cost, run a short benchmark (for example 100k simulated events through the chain) and include the events/sec figure in your notes.
