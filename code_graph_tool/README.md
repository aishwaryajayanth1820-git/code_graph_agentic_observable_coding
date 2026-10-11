# Code Graph tool

A C4 code dependency graph that also serves as the development ledger for agent-built projects. It records nodes (components, service classes, classes, interfaces, config and utility classes), function contracts between them, tasks, ADRs, a utility registry and EVAL verdicts. Humans watch it in a live UI; agents drive it through the `cg` CLI.

Clone it per project. Each project gets its own copy and SQLite database.

## Quick start
```bash
pip install -r requirements.txt                       # CLI is stdlib-only; UI/API needs fastapi + uvicorn
python cg.py install ../project_x --with-claude       # copies the tool to project_x/code_graph (+ .claude skills/agents)
cd ../project_x
python code_graph/cg.py import design/c4_seed.json --actor orchestrator
python code_graph/cg.py serve --port 8770             # http://127.0.0.1:8770/ui/   API docs: /docs
```
Try it with the sample (a small notification platform): `python examples/demo.py` replays an orchestrated build (tasks, review failures, a contract change through an ADR, a new node after the design lock) into `examples/demo.db`; then `python cg.py --db examples/demo.db serve` and open http://127.0.0.1:8770/ui/. To start from an empty graph instead: `python cg.py --db demo.db import examples/sample_seed.json --actor orchestrator`.

## UI
- **Graph:** components are colored C4 boundaries (solid = PLATFORM, dashed = USECASE). Shape shows the node type (hexagon service class, rounded box class, ellipse interface, diamond utility, cut box config) and fill shows the status. At overview zoom only component names show. Clicking a component zooms to its boundary and reveals class names and function-call labels. Clicking a class shows its fields, tasks, ADRs (click for detail and approve/reject), fan-in/out contracts, verdicts and history. Clicking an edge shows the function signature and purpose of the call.
- **Tabs:** Tasks · ADRs · Utilities · EVALs (adherence) · Maturity (metrics) · Checks · Ledger (audit).
- The UI live-refreshes while agents work (it polls a revision counter). Deep links agents can hand to people: `#node=<id>`, `#edge=<id>`, `#view=<tab>` (e.g. `metrics`, `evals`), `#adr=<id>`.

## Design of the tool
```
cg.py                 entry point
codegraph/domain.py   vocabulary: types, C4 ranks, layers, lifecycle, errors   (extend here)
codegraph/db.py       SQLite schema (WAL), transactions, revision counter
codegraph/repository.py  SQL only
codegraph/rules.py    structural validation + governance policies          (extension point: Policy)
codegraph/service.py  use cases; the single API for CLI and HTTP
codegraph/analytics.py  impact, metrics, platform maturity, checks, EVAL adherence
codegraph/loc.py      LOC counters per language                           (extension point: COUNTERS)
codegraph/cli.py      argparse adapter (JSON out, exit 3 = policy violation)
codegraph/api.py      FastAPI adapter + static UI
ui/                   Cytoscape.js (vendored) + fcose compound layout; js/{api,theme,graph,panels,views,app}.js
tests/                pytest suite (governance rules, analytics, CLI, API)
```
- Governance lives in `rules.py` as small `Policy` classes (design lock, locked nodes, ownership, contract change, status gate). Pass a custom list to `GraphService(policies=...)` to adapt them per project.
- `fan_in`/`fan_out` are derived from CALLS edges, never stored, so they cannot drift.
- Configuration (thresholds, approvers, project root) lives in the `meta` table: `cg config set <key> <value> --actor orchestrator`.

Run the tests with `python -m pytest -q`.

Agent-facing documentation lives in the workspace's `.claude/skills/code-graph/` (usage), `.claude/skills/c4-design/` and `.claude/skills/orchestrate-cycle/` (orchestrator), `.claude/agents/` and `.claude/playbooks/`.
