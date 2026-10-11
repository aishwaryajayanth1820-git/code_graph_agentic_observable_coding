# Contract-change escalation protocol

Parallel coders share contracts (CALLS edges). The tool blocks a coder from silently breaking a contract (`CONTRACT_CHANGE`, `LOCKED_NODE`, `OWNERSHIP`, `DESIGN_LOCK` → exit code 3). This protocol turns each block into a coordinated change.

## Coder side (in `.claude/playbooks/coder.md`)
1. `cg adr propose --title --context --decision --consequences --nodes <affected> --actor coder-N`
2. `cg task block <T> --reason "<ADR id>: <one line>" --actor coder-N`
3. Return BLOCKED with the ADR id, the violation JSON (`details.impacted`), and the options considered.

## Orchestrator side
1. **Understand it:** `cg adr get <ADR>`, `cg impact <callee or node> --depth 2`, and `cg task list --status IN_PROGRESS`.
2. **Decide:**
   - **Reject** when the coder can meet the need inside their own node (an adapter, an existing contract, or a utility). Run `cg adr reject <ADR> --note "<alternative>"` and resume the coder with the alternative.
   - **Accept** when the change stays inside the approved design. Run `cg adr accept <ADR> --note ... --actor orchestrator`, plus `cg adr link <ADR> <nodes>` if it must cover more nodes.
   - **Ask the user first** when it changes a PLATFORM contract that is already TESTED/EVALUATED, adds a component, or alters a dependency direction.
3. **Propagate** (accepted only):
   - Every active task in `details.impacted` / `agents_to_notify`: send the running agent a message (SendMessage) with the ADR id, the old and new signature, and what they must change. Nobody resumes until each impacted agent acknowledges.
   - When the callee is baselined or owned by someone else, create a follow-up task for it (`cg task new --adr <ADR> --nodes <callee>`) and dispatch it before, or in parallel with, the blocked coder.
   - New nodes under the design lock: the coder (or you) runs `cg node add ... --adr <ADR>`.
4. **Resume** the blocked coder: re-dispatch with the ADR id (`cg task start <T> --adr <ADR>`) or message the running agent.
5. **Learn:** record the ADR in `design/evolution_log.md`. More than one ADR per cycle for the same component means its contract was under-designed, so revisit the design of that component before the next cycle.
