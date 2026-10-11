/* Right-hand details panel (node, component, edge) and the ADR modal. Pure rendering + link wiring. */
window.CG = window.CG || {};

CG.panels = (() => {
  const T = CG.theme;
  const esc = CG.esc;
  const ctx = { nodesById: {}, edges: [], colors: {}, metrics: null, onNode: () => {}, onEdge: () => {}, onAdr: () => {} };

  const setContext = (c) => Object.assign(ctx, c);
  const nameOf = (id) => ctx.nodesById[id]?.name || id;
  const nodeLink = (id) => `<a data-node="${esc(id)}">${esc(nameOf(id))}</a>`;
  const kv = (rows) => `<div class="kv">${rows.filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `<div>${esc(k)}</div><div>${v}</div>`).join('')}</div>`;
  const sec = (title, body, count) => `<div class="sec"><h4><span>${esc(title)}${count !== undefined ? ` (${count})` : ''}</span></h4>${body}</div>`;
  const text = (s) => (s ? esc(s) : '<span class="muted">—</span>');
  const pre = (s) => (s ? `<pre>${esc(s)}</pre>` : '<span class="muted">—</span>');

  function wire(root) {
    root.querySelectorAll('[data-node]').forEach((a) => { a.onclick = (ev) => { ev.stopPropagation(); ctx.onNode(a.dataset.node); }; });
    root.querySelectorAll('[data-edge]').forEach((a) => { a.onclick = () => ctx.onEdge(Number(a.dataset.edge)); });
    root.querySelectorAll('[data-adr]').forEach((a) => { a.onclick = (ev) => { ev.stopPropagation(); ctx.onAdr(a.dataset.adr); }; });
  }

  function crumbs(d) {
    const chain = [];
    let p = d.parent;
    const seen = new Set();
    while (p && !seen.has(p)) { seen.add(p); chain.unshift(p); p = ctx.nodesById[p]?.parent; }
    return chain.length ? `<span class="crumbs">${chain.map(nodeLink).join(' › ')}</span>` : '';
  }

  function tasksHtml(tasks) {
    if (!tasks.length) return '<span class="muted">No tasks yet.</span>';
    return tasks.slice().reverse().map((t) => `<div class="item">
      <div class="row"><b>${esc(t.id)}</b>${T.pill(t.status, T.task[t.status] || '#9ca3af')}<span class="badge">${esc(t.kind)}</span>
        <span class="muted">${esc(t.agent || 'unassigned')}</span></div>
      <div>${esc(t.title)}</div>
      ${t.description ? `<details><summary>Business context</summary><pre>${esc(t.description)}</pre></details>` : ''}
      ${t.summary ? `<div class="muted">Summary: ${esc(t.summary)}</div>` : ''}
      <div class="muted">${t.started_at ? `started ${esc(CG.fmtDate(t.started_at))}` : `created ${esc(CG.fmtDate(t.created_at))}`}
        ${t.finished_at ? ` · finished ${esc(CG.fmtDate(t.finished_at))}` : ''}${t.adr_id ? ` · <a data-adr="${esc(t.adr_id)}">${esc(t.adr_id)}</a>` : ''}</div>
    </div>`).join('');
  }

  function adrsHtml(adrs) {
    if (!adrs.length) return '<span class="muted">No ADRs.</span>';
    return adrs.map((a) => `<div class="item link" data-adr="${esc(a.id)}"><div class="row"><b>${esc(a.id)}</b>
      ${T.pill(a.status, T.adr[a.status] || '#9ca3af')}</div><div>${esc(a.title)}</div></div>`).join('');
  }

  function callsHtml(edges, dir) {
    if (!edges.length) return '<span class="muted">None.</span>';
    return edges.map((e) => {
      const other = dir === 'out' ? e.to_id : e.from_id;
      return `<div class="item link" data-edge="${e.id}">
        <div class="row">${dir === 'out' ? '→' : '←'} ${nodeLink(other)} <span class="fn">.${esc(e.function_name)}</span></div>
        <code>${esc(e.signature)}</code>${e.purpose ? `<div class="muted">${esc(e.purpose)}</div>` : ''}</div>`;
    }).join('');
  }

  function linksHtml(edges, field) {
    return edges.length ? edges.map((e) => nodeLink(e[field])).join(', ') : '<span class="muted">None.</span>';
  }

  function verdictsHtml(d) {
    const latest = Object.entries(d.latest_verdicts || {});
    if (!latest.length) return '<span class="muted">Not reviewed yet.</span>';
    const chips = latest.map(([id, v]) => T.pill(`${id} ${v}`, T.verdict[v] || '#9ca3af')).join(' ');
    const rows = (d.eval_results || []).slice().reverse().map((r) => `<div class="item"><div class="row"><b>${esc(r.eval_id)}</b>
      ${T.pill(r.verdict, T.verdict[r.verdict])}<span class="muted">${esc(r.reviewer || '')} → coder ${esc(r.coder || '?')}</span></div>
      ${r.notes ? `<div class="muted">${esc(r.notes)}</div>` : ''}<div class="muted">${esc(CG.fmtDate(r.created_at))}</div></div>`).join('');
    return `<div>${chips}</div><details><summary>All results (${d.eval_results.length})</summary>${rows}</details>`;
  }

  function historyHtml(h) {
    return h.map((a) => `<div class="item"><div class="row"><b>${esc(a.op)}</b><span class="muted">${esc(a.actor || '')}
      ${a.task_id ? `· ${esc(a.task_id)}` : ''} · ${esc(CG.fmtDate(a.ts))}</span></div>
      ${a.detail ? `<code>${esc(a.detail.length > 240 ? `${a.detail.slice(0, 240)}…` : a.detail)}</code>` : ''}</div>`).join('');
  }

  function node(d, el) {
    const active = d.tasks.filter((t) => t.status === 'IN_PROGRESS' || t.status === 'BLOCKED');
    const color = ctx.colors[d.component] || '#9ca3af';
    el.innerHTML = `
      <div class="d-head"><h2>${T.shapeSvg(d.type, T.status[d.status])} ${esc(d.name)}</h2>
        <div class="d-sub">${T.pill(d.status, T.status[d.status])}<span class="badge">${esc(d.type)}</span>
          <span class="badge">${esc(d.layer)}</span>${crumbs(d)}</div></div>
      ${active.map((t) => `<div class="banner">${t.status === 'BLOCKED' ? 'Blocked' : 'In progress'}: <b>${esc(t.id)}</b>
        by ${esc(t.agent || '?')} — ${esc(t.title)}</div>`).join('')}
      ${sec('Node', kv([
        ['id', `<code>${esc(d.id)}</code>`],
        ['Business intent', text(d.business_intent)],
        ['Extensibility / pattern', text(d.extensibility)],
        ['Contract', d.contract ? pre(d.contract) : null],
        ['Code path', d.code_path ? `<code>${esc(d.code_path)}</code>` : text(null)],
        ['Lines of code', d.loc ?? text(null)],
        ['Complexity', d.complexity ? `${d.complexity}/10${d.complexity_note ? ` — ${esc(d.complexity_note)}` : ''}` : text(null)],
        ['Changes (tasks)', d.change_count],
        ['Fan-in / fan-out', `${d.fan_in} / ${d.fan_out}`],
        ['Owner', d.owner ? esc(d.owner) : null],
        ['Updated', esc(CG.fmtDate(d.updated_at))],
      ]))}
      ${sec('Tasks', tasksHtml(d.tasks), d.tasks.length)}
      ${sec('ADRs', adrsHtml(d.adrs), d.adrs.length)}
      ${sec('Fan-out · calls', callsHtml(d.calls_out, 'out'), d.calls_out.length)}
      ${sec('Fan-in · called by', callsHtml(d.calls_in, 'in'), d.calls_in.length)}
      ${d.implements.length || d.implemented_by.length ? sec('Interfaces', kv([
        ['Implements', d.implements.length ? linksHtml(d.implements, 'to_id') : null],
        ['Implemented by', d.implemented_by.length ? linksHtml(d.implemented_by, 'from_id') : null]])) : ''}
      ${d.children.length ? sec('Contains', d.children.map((c) => `${T.shapeSvg(c.type, T.status[c.status])} ${nodeLink(c.id)}`).join('<br>'), d.children.length) : ''}
      ${sec('EVAL verdicts', verdictsHtml(d))}
      ${d.utilities.length ? sec('Utilities', d.utilities.map((u) => `<div class="item"><span class="fn">${esc(u.signature || u.name)}</span><div class="muted">${esc(u.purpose)}</div></div>`).join(''), d.utilities.length) : ''}
      <div class="sec"><details><summary>Change ledger (${d.history.length})</summary>${historyHtml(d.history)}</details></div>`;
    el.querySelector('.d-head h2').style.borderLeft = `4px solid ${color}`;
    el.querySelector('.d-head h2').style.paddingLeft = '8px';
    wire(el);
  }

  function statusBar(counts, total) {
    if (!total) return '';
    return `<div class="bar">${T.statusOrder.map((s) => (counts[s] ? `<span title="${s}: ${counts[s]}"
      style="width:${(100 * counts[s]) / total}%;background:${T.status[s]}"></span>` : '')).join('')}</div>
      <div class="muted">${T.statusOrder.filter((s) => counts[s]).map((s) => `${s} ${counts[s]}`).join(' · ')}</div>`;
  }

  function component(d, el) {
    const m = (ctx.metrics?.components_detail || []).find((c) => c.id === d.id) || {};
    const color = ctx.colors[d.id] || '#9ca3af';
    const kids = Object.values(ctx.nodesById).filter((n) => n.parent === d.id)
      .sort((a, b) => a.type.localeCompare(b.type) || a.name.localeCompare(b.name));
    el.innerHTML = `
      <div class="d-head"><h2><span class="swatch ${d.layer === 'USECASE' ? 'dashed' : ''}" style="border-color:${color};background:${color}22;display:inline-block"></span> ${esc(d.name)}</h2>
        <div class="d-sub"><span class="badge">COMPONENT</span><span class="badge">${esc(d.layer)}</span>${T.pill(d.status, T.status[d.status])}</div></div>
      ${sec('Component', kv([
        ['id', `<code>${esc(d.id)}</code>`], ['Business intent', text(d.business_intent)],
        ['Extensibility / pattern', text(d.extensibility)], ['Code path', d.code_path ? `<code>${esc(d.code_path)}</code>` : null]]))}
      ${sec('Progress', statusBar(m.status_counts || {}, m.nodes || 0) || '<span class="muted">No classes yet.</span>')}
      ${sec('Metrics', kv([
        ['Classes', m.nodes], ['Lines of code', m.loc], ['Avg / max complexity', m.avg_complexity != null ? `${m.avg_complexity} / ${m.max_complexity}` : null],
        ['Changes (tasks)', m.change_count], ['Fan-in / fan-out', m.fan_in != null ? `${m.fan_in} / ${m.fan_out}` : null],
        ['Coupling Ca / Ce', m.afferent_coupling != null ? `${m.afferent_coupling} / ${m.efferent_coupling}` : null],
        ['Instability I', m.instability], ['Abstractness A', m.abstractness], ['Distance |A+I−1|', m.distance_main_sequence],
        ['ADRs', m.adrs]]))}
      ${sec('Contains', kids.map((c) => `${T.shapeSvg(c.type, T.status[c.status])} ${nodeLink(c.id)} <span class="muted">${esc(c.type)}</span>`).join('<br>') || '<span class="muted">Empty.</span>', kids.length)}
      ${sec('Depends on', linksHtml(d.depends_out, 'to_id'))}
      ${sec('Depended on by', linksHtml(d.depends_in, 'from_id'))}
      ${sec('Tasks', tasksHtml(d.tasks), d.tasks.length)}
      ${sec('ADRs', adrsHtml(d.adrs), d.adrs.length)}`;
    wire(el);
  }

  function edge(e, el) {
    const siblings = e.kind === 'CALLS'
      ? ctx.edges.filter((x) => x.kind === 'CALLS' && x.to_id === e.to_id && x.function_name === e.function_name && x.id !== e.id) : [];
    el.innerHTML = `
      <div class="d-head"><h2>${e.kind === 'CALLS' ? `<span class="fn" style="font-size:17px">${esc(e.function_name)}()</span>` : esc(e.kind)}</h2>
        <div class="d-sub">${T.pill(e.kind, T.edges[e.kind]?.color || '#9ca3af')}</div></div>
      ${sec('Direction', `${nodeLink(e.from_id)} → ${nodeLink(e.to_id)}`)}
      ${e.kind === 'CALLS' ? sec('Function signature (contract)', pre(e.signature)) : ''}
      ${sec('Purpose of the call', text(e.purpose))}
      ${sec('Provenance', kv([['Created by', text(e.created_by)], ['Task', text(e.task_id)],
        ['Created', esc(CG.fmtDate(e.created_at))], ['Updated', esc(CG.fmtDate(e.updated_at))]]))}
      ${e.kind === 'CALLS' ? sec('Other callers of this contract', siblings.length
        ? siblings.map((x) => `<div class="item link" data-edge="${x.id}">${nodeLink(x.from_id)} <code>${esc(x.signature)}</code></div>`).join('')
        : '<span class="muted">None — changing it only affects the caller above.</span>', siblings.length) : ''}`;
    wire(el);
  }

  function adrModal(a, { onDecide }) {
    const body = document.getElementById('modalBody');
    body.innerHTML = `
      <h2 style="margin:0 0 6px">${esc(a.id)} · ${esc(a.title)}</h2>
      <div class="d-sub">${T.pill(a.status, T.adr[a.status] || '#9ca3af')}<span class="muted">by ${esc(a.author || '?')} · ${esc(CG.fmtDate(a.created_at))}
        ${a.decided_by ? ` · decided by ${esc(a.decided_by)} ${esc(CG.fmtDate(a.decided_at))}` : ''}</span></div>
      ${sec('Context', pre(a.context))}
      ${sec('Decision', pre(a.decision))}
      ${sec('Consequences', pre(a.consequences))}
      ${a.decision_note ? sec('Decision note', pre(a.decision_note)) : ''}
      ${sec('Nodes covered', a.nodes.length ? a.nodes.map(nodeLink).join(', ') : '<span class="muted">None (new-node ADR).</span>')}
      ${a.status === 'PROPOSED' ? `<div class="modal-actions"><input type="text" id="adrNote" placeholder="Decision note (optional)">
        <button class="btn-ok" data-decide="ACCEPTED">Accept</button><button class="btn-no" data-decide="REJECTED">Reject</button></div>` : ''}`;
    body.querySelectorAll('[data-decide]').forEach((b) => {
      b.onclick = () => onDecide(b.dataset.decide, body.querySelector('#adrNote').value);
    });
    wire(body);
    document.getElementById('modal').hidden = false;
  }

  return { setContext, node, component, edge, adrModal, statusBar };
})();
