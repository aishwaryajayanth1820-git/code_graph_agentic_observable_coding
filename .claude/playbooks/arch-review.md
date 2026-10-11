# Architecture review checklist (ARCH)

Apply each ARCH EVAL from `cg eval list --category ARCH`. The checks below are how to gather evidence efficiently.

## Deterministic first
- `cg check`: G01 (platform → use case), G02 (cycles) and G03/G04 (undeclared or concrete cross-component calls) are direct evidence for ARCH-001..004. Quote the finding in your notes.
- `cg metrics` → `components_detail`: flag platform components with instability > 0.3 or distance > 0.5, and cite them in the observations.

## Code versus graph (ARCH-003, ARCH-006)
1. For each node, list its import statements (Grep `^(from|import) ` in the code_path file).
2. Map each imported module to a graph node via `code_path` (`cg node list --q <module>`).
3. Every cross-component import must match a DEPENDS edge between the components, and must target an INTERFACE/SERVICE_CLASS.
4. Every call to another node's method must appear in `calls_out` with the same function name and signature. Missing or drifted edges fail ARCH-006.

## Layering (ARCH-001, ARCH-005)
- PLATFORM code paths must not import USECASE packages, directly or through string-based dynamic import, other than in the declared plugin loader reading a registry.
- For use-case tasks, `cg task get <T>`: if a PLATFORM node is in the task or its file changed, there must be an accepted ADR (`cg adr list --node <id>`). Otherwise ARCH-005 fails.

## Boundaries
- No shared mutable state across components (module globals, singletons).
- Persistence and I/O stay behind ports: adapters are CLASS nodes that IMPLEMENTS an INTERFACE.

## Observations to report even when EVALs pass
Rising `change_count` on platform nodes, repeated ADRs on one component, and use-case vocabulary appearing in platform code.
