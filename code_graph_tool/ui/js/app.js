/* Bootstrap: state, filters, search, tabs, live refresh. Wires the graph, panels and views together. */
(() => {
  const T = CG.theme;
  const esc = CG.esc;
  const $ = (id) => document.getElementById(id);
  const S = {
    data: null, rev: -1, metrics: null, colors: {}, nodesById: {}, view: 'graph', selected: null,
    filters: {
      layers: new Set(Object.keys(T.layers)), types: new Set(Object.keys(T.types)),
      statuses: new Set(T.statusOrder), edges: new Set(Object.keys(T.edges)),
    },
  };

  // ---- filters + legend ----------------------------------------------------
  function checkbox(container, set, value, labelHtml) {
    const l = document.createElement('label');
    l.className = 'check';
    l.innerHTML = `<input type="checkbox" checked> ${labelHtml}`;
    l.querySelector('input').onchange = (ev) => {
      if (ev.target.checked) set.add(value); else set.delete(value);
      CG.graph.applyFilters(S.filters);
    };
    container.appendChild(l);
  }

  function buildFilters() {
    Object.entries(T.layers).forEach(([k, label]) => checkbox($('filterLayer'), S.filters.layers, k,
      `<span class="swatch ${k === 'USECASE' ? 'dashed' : ''}" style="border-color:#9ca3af"></span>${esc(label)}`));
    Object.entries(T.types).forEach(([k, t]) => checkbox($('filterType'), S.filters.types, k, `${T.shapeSvg(k)}${esc(t.label)}`));
    T.statusOrder.forEach((s) => checkbox($('filterStatus'), S.filters.statuses, s,
      `<span class="swatch" style="border-color:${T.status[s]};background:${T.status[s]}"></span>${esc(s)}`));
    Object.entries(T.edges).forEach(([k, e]) => checkbox($('filterEdge'), S.filters.edges, k,
      `<span class="swatch" style="border-color:${e.color};border-radius:0;height:3px;border-width:1px;background:${e.color}"></span>${esc(e.label)}`));
  }

  function renderLegend() {
    const comps = S.data.nodes.filter((n) => n.type === 'COMPONENT').sort((a, b) => a.layer.localeCompare(b.layer) || a.name.localeCompare(b.name));
    $('componentLegend').innerHTML = comps.map((c) => `<div data-comp="${esc(c.id)}"><span class="swatch ${c.layer === 'USECASE' ? 'dashed' : ''}"
      style="border-color:${S.colors[c.id]};background:${S.colors[c.id]}22"></span>${esc(c.name)}</div>`).join('') || '<span class="muted">No components yet.</span>';
    $('componentLegend').querySelectorAll('[data-comp]').forEach((d) => {
      d.onclick = () => { showView('graph'); CG.graph.focusComponent(d.dataset.comp); openDetails({ kind: 'component', id: d.dataset.comp }); };
    });
  }

  function renderStats() {
    const m = S.metrics;
    $('projectName').textContent = `${S.data.meta.project || 'unnamed project'}${S.data.meta.design_locked ? ' · design locked' : ''}`;
    $('stats').innerHTML = `<b>${m.components}</b> components · <b>${m.code_nodes}</b> classes · <b>${S.data.edges.filter((e) => e.kind === 'CALLS').length}</b> calls<br>
      <b>${m.progress_pct}%</b> done · <b>${m.evaluated_pct}%</b> evaluated`;
  }

  // ---- details -------------------------------------------------------------
  async function openDetails(sel) {
    S.selected = sel;
    const el = $('details');
    try {
      if (sel.kind === 'edge') {
        const e = S.data.edges.find((x) => x.id === sel.id);
        if (e) CG.panels.edge(e, el);
        return;
      }
      const d = await CG.api.get(`/nodes/${encodeURIComponent(sel.id)}`);
      if (S.selected !== sel) return;  // a newer selection won
      if (d.type === 'COMPONENT') CG.panels.component(d, el); else CG.panels.node(d, el);
    } catch (err) {
      el.innerHTML = `<div class="empty">${esc(err.message)}</div>`;
    }
  }

  function showNode(id) {
    showView('graph');
    CG.graph.selectNode(id);
    openDetails({ kind: S.nodesById[id]?.type === 'COMPONENT' ? 'component' : 'node', id });
  }

  function showEdge(id) {
    showView('graph');
    CG.graph.selectEdge(id);
    openDetails({ kind: 'edge', id });
  }

  async function openAdr(id) {
    try {
      const a = await CG.api.get(`/adrs/${encodeURIComponent(id)}`);
      CG.panels.adrModal(a, {
        onDecide: async (status, note) => {
          try {
            await CG.api.post(`/adrs/${encodeURIComponent(id)}/decide`, { status, note: note || null });
            closeModal();
            await load(true);
          } catch (err) { CG.toast(err.message); }
        },
      });
    } catch (err) { CG.toast(err.message); }
  }

  function closeModal() { $('modal').hidden = true; }

  // ---- views ---------------------------------------------------------------
  function showView(name) {
    S.view = name;
    document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
    $('view').hidden = name === 'graph';
    if (name === 'graph') CG.graph.resize(); else CG.views.render(name, $('view'));
  }

  // ---- search --------------------------------------------------------------
  function setupSearch() {
    const input = $('search');
    const box = $('suggest');
    let items = [];
    let idx = -1;
    const pick = (i) => { if (items[i]) { showNode(items[i].id); box.hidden = true; input.blur(); } };
    const draw = () => {
      box.innerHTML = items.map((n, i) => `<div data-i="${i}" class="${i === idx ? 'on' : ''}">${T.shapeSvg(n.type, T.status[n.status])}
        ${esc(n.name)}<span class="t">${esc(n.type)}</span></div>`).join('');
      box.hidden = !items.length;
      box.querySelectorAll('[data-i]').forEach((d) => { d.onmousedown = () => pick(Number(d.dataset.i)); });
    };
    input.oninput = () => {
      const words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
      items = words.length ? S.data.nodes.filter((n) => words.every((w) => `${n.name} ${n.id} ${n.business_intent || ''} ${n.code_path || ''}`
        .toLowerCase().includes(w))).slice(0, 12) : [];
      idx = items.length ? 0 : -1;
      draw();
    };
    input.onkeydown = (ev) => {
      if (ev.key === 'ArrowDown') { idx = Math.min(items.length - 1, idx + 1); draw(); ev.preventDefault(); }
      if (ev.key === 'ArrowUp') { idx = Math.max(0, idx - 1); draw(); ev.preventDefault(); }
      if (ev.key === 'Enter') pick(idx);
      if (ev.key === 'Escape') { box.hidden = true; }
    };
    input.onblur = () => setTimeout(() => { box.hidden = true; }, 150);
  }

  // ---- data ----------------------------------------------------------------
  async function load(force) {
    const { rev } = await CG.api.get('/rev');
    if (!force && rev === S.rev) return;
    S.rev = rev;
    const [graph, metrics] = await Promise.all([CG.api.get('/graph'), CG.api.get('/metrics')]);
    S.data = graph;
    S.metrics = metrics;
    S.nodesById = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    S.colors = CG.graph.render(graph);
    CG.graph.applyFilters(S.filters);
    CG.panels.setContext({ nodesById: S.nodesById, edges: graph.edges, colors: S.colors, metrics });
    CG.views.setContext({ nodesById: S.nodesById });
    renderLegend();
    renderStats();
    if (S.selected) openDetails(S.selected);
    if (S.view !== 'graph') CG.views.render(S.view, $('view'));
  }

  function init() {
    buildFilters();
    setupSearch();
    CG.graph.init($('cy'), {
      onNode: (id) => openDetails({ kind: 'node', id }),
      onComponent: (id) => openDetails({ kind: 'component', id }),
      onEdge: (e) => openDetails({ kind: 'edge', id: e.id }),
      onBackground: () => { S.selected = null; $('details').innerHTML = '<div class="empty">Select a component, class or edge.</div>'; },
    });
    CG.panels.setContext({ onNode: showNode, onEdge: showEdge, onAdr: openAdr });
    CG.views.setContext({ onNode: showNode, onAdr: openAdr });
    document.querySelectorAll('#tabs button').forEach((b) => { b.onclick = () => showView(b.dataset.view); });
    $('btnReset').onclick = () => CG.graph.reset();
    $('btnRelayout').onclick = () => CG.graph.relayout();
    $('allLabels').onchange = (ev) => CG.graph.setAllLabels(ev.target.checked);
    $('collapseLeft').onclick = () => { document.querySelector('.layout').classList.toggle('left-collapsed'); setTimeout(CG.graph.resize, 50); };
    $('modalClose').onclick = closeModal;
    $('modal').onclick = (ev) => { if (ev.target === $('modal')) closeModal(); };
    document.addEventListener('keydown', (ev) => {
      if (ev.key !== 'Escape' || ev.target.tagName === 'INPUT') return;
      if (!$('modal').hidden) closeModal(); else CG.graph.reset();
    });
    load(true).then(openDeepLink).catch((err) => CG.toast(`Load failed: ${err.message}`));
    setInterval(() => load(false).catch(() => {}), 4000);
  }

  /* Deep links agents can hand to humans: #node=<id> | #edge=<id> | #view=<tab> | #adr=<id> (combinable with node/view) */
  function openDeepLink() {
    const p = new URLSearchParams(location.hash.slice(1));
    setTimeout(() => {
      if (p.get('node') && S.nodesById[p.get('node')]) showNode(p.get('node'));
      else if (p.get('edge')) showEdge(Number(p.get('edge')));
      else if (p.get('view') && CG.views.has(p.get('view'))) showView(p.get('view'));
      if (p.get('adr')) openAdr(p.get('adr'));
    }, 300);
  }

  init();
})();
