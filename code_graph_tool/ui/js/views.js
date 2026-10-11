/* Full-width tab views over the ledger: tasks, ADRs, utilities, EVALs, maturity, checks, audit. */
window.CG = window.CG || {};

CG.views = (() => {
  const T = CG.theme;
  const esc = CG.esc;
  const ctx = { nodesById: {}, onNode: () => {}, onAdr: () => {} };
  const setContext = (c) => Object.assign(ctx, c);

  const nodeLink = (id) => `<a data-node="${esc(id)}">${esc(ctx.nodesById[id]?.name || id)}</a>`;
  const num = (v) => (v === null || v === undefined ? '—' : v);
  const pct = (v) => (v === null || v === undefined ? '—' : `${v}%`);
  const table = (heads, rows) => `<div class="table-wrap"><table><thead><tr>${heads.map((h) => (
    typeof h === 'string' ? `<th>${esc(h)}</th>` : `<th class="num">${esc(h.n)}</th>`)).join('')}</tr></thead>
    <tbody>${rows.join('') || `<tr><td colspan="${heads.length}" class="muted">Nothing yet.</td></tr>`}</tbody></table></div>`;
  const card = (value, label, hint) => `<div class="card"><div class="v${String(value).length > 9 ? ' sm' : ''}">${value}</div><div class="l">${esc(label)}</div>${hint ? `<div class="h">${esc(hint)}</div>` : ''}</div>`;
  const rateBar = (r) => (r === null || r === undefined ? '—' : `<div style="display:flex;gap:6px;align-items:center">
    <div class="bar" style="width:80px"><span style="width:${r * 100}%;background:${r >= 0.8 ? '#22c55e' : r >= 0.5 ? '#f59e0b' : '#ef4444'}"></span></div>${Math.round(r * 100)}%</div>`);

  function wire(el) {
    el.querySelectorAll('[data-node]').forEach((a) => { a.onclick = (ev) => { ev.stopPropagation(); ctx.onNode(a.dataset.node); }; });
    el.querySelectorAll('[data-adr]').forEach((a) => { a.onclick = () => ctx.onAdr(a.dataset.adr); });
  }

  async function tasks(el) {
    const all = await CG.api.get('/tasks');
    const statuses = ['ALL', 'OPEN', 'IN_PROGRESS', 'BLOCKED', 'DONE', 'CANCELLED'];
    const draw = (filter) => {
      const rows = all.filter((t) => filter === 'ALL' || t.status === filter).reverse().map((t) => `<tr>
        <td><b>${esc(t.id)}</b></td><td>${T.pill(t.status, T.task[t.status])}</td><td><span class="badge">${esc(t.kind)}</span></td>
        <td>${esc(t.title)}${t.description ? `<details><summary>Business context</summary><pre>${esc(t.description)}</pre></details>` : ''}
          ${t.summary ? `<div class="muted">${esc(t.summary)}</div>` : ''}</td>
        <td>${esc(t.agent || '')}</td><td>${t.nodes.map(nodeLink).join(', ')}</td>
        <td>${t.adr_id ? `<a data-adr="${esc(t.adr_id)}">${esc(t.adr_id)}</a>` : ''}</td>
        <td class="muted">${esc(CG.fmtDate(t.started_at))}</td><td class="muted">${esc(CG.fmtDate(t.finished_at))}</td></tr>`);
      el.querySelector('#taskTable').innerHTML = table(['Task', 'Status', 'Kind', 'Title', 'Agent', 'Nodes', 'ADR', 'Started', 'Finished'], rows);
      wire(el);
    };
    el.innerHTML = `<h2>Tasks</h2><p class="lead">Every task start counts one change on each node it touches. Blocked tasks are escalations waiting for the orchestrator.</p>
      <div class="toolbar">${statuses.map((s) => `<button data-f="${s}">${s} ${s === 'ALL' ? all.length : all.filter((t) => t.status === s).length}</button>`).join('')}</div>
      <div id="taskTable"></div>`;
    el.querySelectorAll('[data-f]').forEach((b) => { b.onclick = () => draw(b.dataset.f); });
    draw('ALL');
  }

  async function adrs(el) {
    const all = await CG.api.get('/adrs');
    const rows = all.slice().reverse().map((a) => `<tr class="click" data-adr="${esc(a.id)}"><td><b>${esc(a.id)}</b></td>
      <td>${T.pill(a.status, T.adr[a.status])}</td><td>${esc(a.title)}</td><td>${esc(a.author || '')}</td>
      <td class="muted">${esc(CG.fmtDate(a.created_at))}</td><td>${esc(a.decided_by || '')}</td></tr>`);
    el.innerHTML = `<h2>Architecture decision records</h2><p class="lead">Changes to TESTED/EVALUATED nodes, contract changes between agents and new nodes after the design lock all need an ACCEPTED ADR. Click a row to review, accept or reject it.</p>
      ${table(['ADR', 'Status', 'Title', 'Author', 'Created', 'Decided by'], rows)}`;
  }

  async function utilities(el) {
    const all = await CG.api.get('/utilities');
    const draw = (q) => {
      const words = q.toLowerCase().split(/\s+/).filter(Boolean);
      const rows = all.filter((u) => words.every((w) => `${u.name} ${u.purpose} ${u.signature || ''} ${u.module_path || ''}`.toLowerCase().includes(w)))
        .map((u) => `<tr><td class="fn">${esc(u.name)}</td><td><code>${esc(u.signature || '')}</code></td><td>${esc(u.purpose)}</td>
          <td><code>${esc(u.module_path || '')}</code></td><td>${u.node_id ? nodeLink(u.node_id) : ''}</td><td class="muted">${esc(u.created_by || '')}</td></tr>`);
      el.querySelector('#utilTable').innerHTML = table(['Name', 'Signature', 'Purpose', 'Module', 'Node', 'Added by'], rows);
      wire(el);
    };
    el.innerHTML = `<h2>Utility registry</h2><p class="lead">Agents look here (cg util find) before writing a helper. ${all.length} registered.</p>
      <div class="toolbar"><input type="search" id="utilQ" placeholder="Filter utilities…"></div><div id="utilTable"></div>`;
    el.querySelector('#utilQ').oninput = (ev) => draw(ev.target.value);
    draw('');
  }

  async function evals(el) {
    const [catalog, report] = await Promise.all([CG.api.get('/evals'), CG.api.get('/evals/report')]);
    const rows = catalog.map((e) => {
      const r = report.evals[e.id] || {};
      return `<tr><td><b>${esc(e.id)}</b></td><td><span class="badge">${esc(e.category)}</span></td><td>${esc(e.severity)}</td>
        <td>${esc(e.title)}<details><summary>Rule</summary><pre>${esc(e.rule)}</pre>${e.check_method ? `<div class="muted">Check: ${esc(e.check_method)}</div>` : ''}</details></td>
        <td class="num">${num(r.results)}</td><td class="num">${num(r.PASS || 0)}</td><td class="num">${num(r.FAIL || 0)}</td>
        <td class="num">${num(r.open_fail)}</td><td>${rateBar(r.first_pass_rate)}</td></tr>`;
    });
    const coders = Object.entries(report.coders).map(([c, v]) => `<tr><td>${esc(c)}</td><td class="num">${v.pairs}</td>
      <td class="num">${v.results}</td><td>${rateBar(v.first_pass_rate)}</td></tr>`);
    el.innerHTML = `<h2>EVAL adherence</h2>
      <p class="lead">First-pass rate = share of (node, EVAL) pairs whose first review verdict was PASS, i.e. the coder followed the EVAL without being told. Low first-pass EVALs are the guidance that belongs in coder prompts and skills.</p>
      <div class="cards">${card(catalog.length, 'EVALs in catalog')}${card(report.least_followed.slice(0, 3).join(', ') || '—', 'Least followed')}
        ${card(report.never_checked.length, 'Never checked', report.never_checked.slice(0, 6).join(', '))}</div>
      ${table(['EVAL', 'Category', 'Severity', 'Title', { n: 'Results' }, { n: 'Pass' }, { n: 'Fail' }, { n: 'Open fails' }, 'First-pass'], rows)}
      <h2 style="margin-top:22px">By coder agent</h2>
      ${table(['Coder', { n: 'Node×EVAL pairs' }, { n: 'Results' }, 'First-pass'], coders)}`;
  }

  async function metrics(el) {
    const m = await CG.api.get('/metrics');
    const pm = m.platform_maturity;
    const rows = m.components_detail.map((c) => `<tr><td>${nodeLink(c.id)}</td><td><span class="badge">${esc(c.layer)}</span></td>
      <td style="min-width:140px">${CG.panels.statusBar(c.status_counts, c.nodes)}</td><td class="num">${c.nodes}</td><td class="num">${c.loc}</td>
      <td class="num">${num(c.avg_complexity)}</td><td class="num">${c.change_count}</td><td class="num">${c.fan_in}/${c.fan_out}</td>
      <td class="num">${c.afferent_coupling}/${c.efferent_coupling}</td><td class="num">${c.instability}</td><td class="num">${c.abstractness}</td>
      <td class="num">${c.distance_main_sequence}</td><td class="num">${c.adrs}</td></tr>`);
    el.innerHTML = `<h2>Progress and platform maturity</h2>
      <p class="lead">A maturing platform is stable (low instability, few post-baseline changes) and absorbs new use cases without edits.</p>
      <div class="cards">${card(pct(m.progress_pct), 'Code nodes done', 'COMPLETED + TESTED + EVALUATED')}
        ${card(pct(m.evaluated_pct), 'Evaluated')}${card(m.code_nodes, 'Code nodes', `${m.components} components`)}${card(m.loc, 'Lines of code')}
        ${card(Object.entries(m.tasks).map(([k, v]) => `${v} ${k}`).join(' · ') || '0', 'Tasks')}
        ${card(Object.entries(m.adrs).map(([k, v]) => `${v} ${k}`).join(' · ') || '0', 'ADRs')}</div>
      <h2>Platform maturity signals</h2>
      <div class="cards">${card(pct(pm.usecase_tasks_touching_platform_pct), 'Use-case tasks that changed the platform', `lower is better · ${pm.usecase_tasks} use-case tasks`)}
        ${card(num(pm.platform_instability_avg), 'Platform instability (avg I)', 'Ce/(Ca+Ce); platforms should trend to 0')}
        ${card(num(pm.platform_change_per_node), 'Platform changes per node', 'task starts per platform class')}
        ${card(pct(pm.platform_evaluated_pct), 'Platform evaluated')}
        ${card(pm.platform_adrs, 'Platform ADRs', 'changes to baselined platform nodes')}
        ${card(pm.dependency_direction_violations, 'Platform → use-case edges', 'must be 0')}</div>
      <h2>Components</h2>
      ${table(['Component', 'Layer', 'Status', { n: 'Classes' }, { n: 'LOC' }, { n: 'Avg cx' }, { n: 'Changes' }, { n: 'Fan in/out' }, { n: 'Ca/Ce' }, { n: 'I' }, { n: 'A' }, { n: 'D' }, { n: 'ADRs' }], rows)}`;
  }

  async function checks(el) {
    const c = await CG.api.get('/check');
    const rules = { G01: 'Platform must not depend on use case', G02: 'No component dependency cycles', G03: 'Cross-component calls need a declared DEPENDS',
      G04: 'Cross-component calls target an interface or service', G05: 'Every class has a parent', G06: 'Done nodes record path, LOC, complexity',
      G07: 'Complexity within threshold', G08: 'Fan-out within threshold', G09: 'Class size within threshold', G11: 'Interfaces have implementers' };
    const rows = c.findings.map((f) => `<tr><td class="sev-${esc(f.severity)}">${esc(f.severity)}</td><td><b>${esc(f.rule)}</b> <span class="muted">${esc(rules[f.rule] || '')}</span></td>
      <td>${nodeLink(f.node)}</td><td>${esc(f.message)}</td></tr>`);
    el.innerHTML = `<h2>Architecture checks ${c.passed ? T.pill('PASSED', '#22c55e') : T.pill('FAILED', '#ef4444')}</h2>
      <p class="lead">Deterministic rules over the graph (same as <code>cg check</code>). Thresholds: complexity ≤ ${c.thresholds.max_complexity}, fan-out ≤ ${c.thresholds.max_fan_out}, LOC ≤ ${c.thresholds.max_loc}.</p>
      ${table(['Severity', 'Rule', 'Node', 'Finding'], rows)}`;
  }

  async function audit(el) {
    const rows = (await CG.api.get('/audit?limit=200')).map((a) => `<tr><td class="muted">${esc(CG.fmtDate(a.ts))}</td><td>${esc(a.actor || '')}</td>
      <td>${esc(a.task_id || '')}</td><td><b>${esc(a.op)}</b></td><td>${ctx.nodesById[a.target] ? nodeLink(a.target) : esc(a.target || '')}</td>
      <td><code>${esc((a.detail || '').slice(0, 200))}</code></td></tr>`);
    el.innerHTML = `<h2>Change ledger</h2><p class="lead">Last 200 mutations by agents and humans.</p>${table(['When', 'Actor', 'Task', 'Operation', 'Target', 'Detail'], rows)}`;
  }

  const VIEWS = { tasks, adrs, utilities, evals, metrics, checks, audit };

  async function render(name, el) {
    el.innerHTML = '<div class="muted">Loading…</div>';
    try {
      await VIEWS[name](el);
      wire(el);
    } catch (err) {
      el.innerHTML = `<div class="sev-ERROR">Failed to load: ${esc(err.message)}</div>`;
    }
  }

  return { setContext, render, has: (n) => n in VIEWS };
})();
