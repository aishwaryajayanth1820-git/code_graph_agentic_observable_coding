# AGENTS.md

Guidance for AI coding agents working on this repository. People should start with [README.md](README.md).

## What this is
A C4 code graph tool (`code_graph_tool/`) and an agent layer (`.claude/`: agents, skills, playbooks) that lets coding agents plan, build and review software against a shared ledger. The graph records C4 nodes, function contracts (CALLS edges), tasks, ADRs, a utility registry and EVAL verdicts, and its policies block unapproved changes.

## Setup and checks
```bash
cd code_graph_tool
pip install -r requirements.txt     # Python 3.10+
python -m pytest -q                 # must pass
python examples/demo.py             # must finish with "check: clean"
python cg.py --db examples/demo.db serve --port 8770   # UI at http://127.0.0.1:8770/ui/
```

## Code map
- `codegraph/domain.py`: vocabulary (node types, layers, lifecycle, errors). Extend types here.
- `codegraph/service.py`: every use case. The CLI, HTTP API and UI all go through `GraphService`.
- `codegraph/rules.py`: validation and governance policies (small `Policy` classes).
- `codegraph/analytics.py`: impact, metrics, checks G01–G13, EVAL adherence. Deterministic, no I/O.
- `codegraph/repository.py`: SQL only. `codegraph/db.py`: schema (SQLite, WAL).
- `codegraph/cli.py`, `codegraph/api.py`: thin adapters. `ui/`: static JS, no build step, vendored Cytoscape.js.
- `tests/test_codegraph.py`: the pytest suite. `examples/`: generic sample seed and demo.

## Rules
- Keep adapters thin: new behaviour goes into `GraphService`, rules into `rules.py`, measurements into `analytics.py`.
- The CLI uses only the standard library. Output is JSON on stdout; errors are JSON on stderr with exit codes 1 (unexpected), 2 (invalid input or not found) and 3 (policy violation).
- `fan_in`/`fan_out` are derived from CALLS edges and never stored.
- Add a test for every behaviour change; keep the demo ending with a clean `cg check`.
- Agent definitions and `SKILL.md` files stay short (about 20–40 lines); detail goes in `.claude/playbooks/` and `reference/` files.
- Keep examples generic. The sample project is a notification platform.
- Bundled libraries in `ui/vendor/` are third-party; don't edit them (see THIRD_PARTY_NOTICES.md).

## Using the graph as an agent on another project
Read `.claude/skills/code-graph/SKILL.md`. Coders follow `.claude/playbooks/coder.md`; reviewers follow `.claude/playbooks/reviewer.md`. Treat exit code 3 as a stop: propose an ADR and escalate, never work around it.
