# Authoring EVALs

An EVAL is a binary, checkable rule that a reviewer agent applies to a node. It is stored in the graph (`cg eval add` / `cg eval import`), and verdicts are recorded per node (`cg eval record`).

## Anatomy
| Field | Rule |
|---|---|
| `id` | `<PREFIX>-<NNN>`: ARCH, APP, CODE, BIZ, SEC, PERF. Baseline = 001–099; project-specific = 100+ |
| `category` | `ARCH` · `APP_DESIGN` · `CODE` · `BUSINESS` · `SECURITY` · `PERFORMANCE` (decides which reviewer owns it) |
| `title` | Short imperative |
| `rule` | One observable, testable statement. No "should consider" |
| `check_method` | How to check it, so every reviewer does it the same way: `cg check G01`, a grep, a test command, or "read X and confirm Y" |
| `severity` | `BLOCKER` (cannot be EVALUATED) · `MAJOR` · `MINOR` |

## Kinds to write for every project
1. **Invariants (BIZ).** Business facts that must always hold, taken from the requirement. Example: "Messages per recipient per day never exceed the configured quota at any point in time; property test with 10k simulated events."
2. **ArchUnit-style dependency rules (ARCH).** Allowed and forbidden dependencies. Prefer ones that `cg check` or an import grep proves. Example: "Nothing under `src/` imports from `plugins/`."
3. **Interface contract EVALs (APP/CODE).** The signature in the graph equals the signature in code, every CALLS-in function has a unit test, errors are part of the contract.
4. **Extensibility EVALs (APP).** For each extension point, "adding use case X touches only files Y". Reviewers verify this by listing what a new plugin would need.
5. **Platform maturity EVALs (ARCH).** "This use-case task changed no PLATFORM node, or the change has an ADR."
6. **NFR EVALs (SEC/PERF).** From the requirement's traffic, data and trust assumptions.

## Writing rules
- One concern per EVAL, so verdicts stay unambiguous and first-pass rates stay meaningful.
- Prefer deterministic checks. If an EVAL is checked by reading code every cycle, consider adding a `cg check` rule or a test.
- Put the expected fix pattern in the rule when you know it (for example "use the injected Clock; never call datetime.now() directly").

## Lifecycle (evolution mode)
- A low `first_pass_rate`: keep the EVAL and strengthen the coder guidance (`.claude/playbooks/coder-lessons.md`, the task brief). Never relax the EVAL to make numbers look better.
- `never_checked`: the reviewer brief does not cover it. Fix the brief.
- Reviewers propose new EVALs for gaps they find. The orchestrator adds the good ones with `cg eval add`.

## Examples (notification platform)
```json
[
  {"id": "BIZ-101", "category": "BUSINESS", "severity": "BLOCKER", "title": "Rate limit never exceeded",
   "rule": "Messages per recipient per day never exceed the channel's configured quota, including concurrent dispatches.",
   "check_method": "Property test over simulated traffic bursts; read the dispatch path for check-then-act races."},
  {"id": "APP-101", "category": "APP_DESIGN", "severity": "MAJOR", "title": "New channel = new plugin only",
   "rule": "Adding a delivery channel requires a new plugin file and a plugins.json entry, with no edits under src/dispatch_engine.",
   "check_method": "List the files a hypothetical 'Push notifications' plugin would touch."},
  {"id": "PERF-101", "category": "PERFORMANCE", "severity": "MAJOR", "title": "Per-event path is O(1)",
   "rule": "SubscriptionFilter + Dispatcher.dispatch do no I/O and no scans over recipients or history per event.",
   "check_method": "Read the dispatch call chain; micro-benchmark 100k events."}
]
```
