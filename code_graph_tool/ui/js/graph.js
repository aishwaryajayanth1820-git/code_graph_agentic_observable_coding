/* Cytoscape rendering of the C4 graph: components are compound boundaries, classes live inside them.
 * Visual state is derived from `state` by restyle(), so every interaction just edits state and restyles. */
window.CG = window.CG || {};

CG.graph = (() => {
  const T = CG.theme;
  let cy = null;
  let handlers = {};
  let posKey = 'cg.pos';
  const state = { focus: null, selected: null, allLabels: false };

  const LAYOUT = {
    name: 'fcose', quality: 'proof', animate: false, nodeDimensionsIncludeLabels: true, packComponents: true,
    // Cross-component edges are long and loose so they do not drag C4 boundaries into each other.
    nodeRepulsion: () => 25000,
    idealEdgeLength: (e) => (e.data('kind') === 'DEPENDS' ? 380 : e.data('cross') ? 300 : 90),
    edgeElasticity: (e) => (e.data('cross') || e.data('kind') === 'DEPENDS' ? 0.02 : 0.35),
    nestingFactor: 0.1, gravity: 0.1, gravityCompound: 1.6, gravityRangeCompound: 1.5, numIter: 6000,
    tile: true, tilingPaddingVertical: 30, tilingPaddingHorizontal: 30, componentSpacing: 120,
  };

  const STYLE = [
    { selector: 'node', style: {
      label: 'data(label)', color: '#e5e7eb', 'font-size': 14, 'text-valign': 'bottom', 'text-margin-y': 4,
      'text-opacity': 0, 'text-background-color': '#0b0f17', 'text-background-opacity': 0.8,
      'text-background-padding': 2, 'text-background-shape': 'round-rectangle', 'text-wrap': 'ellipsis',
      'text-max-width': 150,
    } },
    { selector: 'node.code', style: {
      shape: (n) => (T.types[n.data('type')] || T.types.CLASS).shape, 'background-color': 'data(fill)',
      'border-color': 'data(color)', 'border-width': 2, width: 'data(size)', height: 'data(size)',
    } },
    { selector: 'node.code.compound', style: {
      shape: 'round-rectangle', 'background-color': 'data(fill)', 'background-opacity': 0.12,
      'border-color': 'data(fill)', 'text-valign': 'top', 'text-margin-y': -4, padding: 16,
    } },
    { selector: 'node.component', style: {
      shape: 'round-rectangle', 'background-color': 'data(color)', 'background-opacity': 0.07,
      'border-color': 'data(color)', 'border-width': 3, color: 'data(color)', 'font-size': 'data(font)', 'font-weight': 700,
      'text-opacity': 1, 'text-valign': 'top', 'text-margin-y': -8, 'text-background-opacity': 0, padding: 30,
      width: 140, height: 90, 'text-max-width': 1600, 'text-wrap': 'none',
    } },
    { selector: 'node.component.usecase', style: { 'border-style': 'dashed' } },
    { selector: 'node.active', style: { 'border-color': '#fbbf24', 'border-width': 5, 'border-style': 'double' } },
    { selector: 'edge', style: {
      'curve-style': 'bezier', width: 1.6, 'line-color': T.edges.CALLS.color, 'target-arrow-color': T.edges.CALLS.color,
      'target-arrow-shape': 'triangle', 'arrow-scale': 0.9, opacity: 0.75, label: 'data(label)', 'font-size': 11,
      color: '#bfdbfe', 'text-rotation': 'autorotate', 'text-opacity': 0, 'text-background-color': '#0b0f17',
      'text-background-opacity': 0.85, 'text-background-padding': 1,
    } },
    { selector: 'edge.depends', style: {
      width: 3.5, 'line-style': 'dashed', 'line-color': T.edges.DEPENDS.color, 'target-arrow-color': T.edges.DEPENDS.color,
      opacity: 0.5, color: '#e9d5ff',
    } },
    { selector: 'edge.implements', style: {
      'line-style': 'dotted', 'line-color': T.edges.IMPLEMENTS.color, 'target-arrow-color': T.edges.IMPLEMENTS.color,
      'target-arrow-fill': 'hollow', color: '#e5e7eb',
    } },
    { selector: 'edge.uses', style: {
      'line-style': 'dotted', width: 1, 'line-color': T.edges.USES.color, 'target-arrow-color': T.edges.USES.color,
      'target-arrow-shape': 'vee', opacity: 0.35,
    } },
    { selector: '.lbl', style: { 'text-opacity': 1 } },
    { selector: '.faded', style: { opacity: 0.1 } },
    { selector: 'node.component.faded', style: { opacity: 0.3 } },
    { selector: 'edge.hl', style: { width: 3, opacity: 1, 'z-index': 99 } },
    { selector: 'node:selected', style: { 'border-color': '#ffffff', 'border-width': 4 } },
    { selector: 'edge:selected', style: { width: 4, opacity: 1, 'text-opacity': 1, 'z-index': 100 } },
    { selector: '.filtered', style: { display: 'none' } },
  ];

  function componentColors(nodes) {
    const comps = nodes.filter((n) => n.type === 'COMPONENT').map((n) => n.id).sort();
    return Object.fromEntries(comps.map((id, i) => [id, T.palette[i % T.palette.length]]));
  }

  function componentOf(id, byId) {
    const seen = new Set();
    let cur = byId[id];
    while (cur && cur.parent && !seen.has(cur.id)) { seen.add(cur.id); cur = byId[cur.parent]; }
    return cur ? cur.id : id;
  }

  function toElements(data) {
    const byId = Object.fromEntries(data.nodes.map((n) => [n.id, n]));
    const colors = componentColors(data.nodes);
    const parents = new Set(data.nodes.filter((n) => n.parent).map((n) => n.parent));
    const compFont = Math.round(Math.max(30, Math.sqrt(data.nodes.length) * 5.5));  // readable at overview zoom
    const els = data.nodes.map((n) => {
      const comp = componentOf(n.id, byId);
      const isComp = n.type === 'COMPONENT';
      const classes = [isComp ? 'component' : 'code', n.layer.toLowerCase()];
      if (parents.has(n.id)) classes.push('compound');
      if (n.active) classes.push('active');
      return {
        group: 'nodes',
        data: {
          id: n.id, parent: n.parent && byId[n.parent] ? n.parent : undefined, label: n.name, type: n.type,
          layer: n.layer, status: n.status, component: comp, color: colors[comp] || '#9ca3af', font: compFont,
          fill: T.status[n.status] || '#6b7280', size: n.loc ? Math.round(24 + Math.min(40, Math.sqrt(n.loc) * 2.4)) : 26,
        },
        classes: classes.join(' '),
      };
    });
    for (const e of data.edges) {
      if (!byId[e.from_id] || !byId[e.to_id]) continue;
      const label = e.kind === 'CALLS' ? e.function_name : e.kind.toLowerCase();
      const cross = componentOf(e.from_id, byId) !== componentOf(e.to_id, byId);
      els.push({ group: 'edges', data: { id: `e${e.id}`, source: e.from_id, target: e.to_id, kind: e.kind, label, raw: e, cross },
        classes: e.kind.toLowerCase() });
    }
    return { els, colors };
  }

  function savePositions() {
    const pos = {};
    cy.nodes().filter((n) => !n.isParent()).forEach((n) => { pos[n.id()] = n.position(); });
    try { localStorage.setItem(posKey, JSON.stringify(pos)); } catch (_) { /* storage unavailable */ }
  }

  function loadPositions() {
    try { return JSON.parse(localStorage.getItem(posKey) || '{}'); } catch (_) { return {}; }
  }

  function runLayout(randomize) {
    const layout = cy.layout({ ...LAYOUT, randomize });
    layout.one('layoutstop', () => { savePositions(); if (randomize) cy.fit(undefined, 40); });
    layout.run();
  }

  function restyle() {
    cy.batch(() => {
      cy.elements().removeClass('faded hl lbl');
      let lit = null;
      if (state.focus) {
        const c = cy.getElementById(state.focus);
        if (c.nonempty()) {
          const inside = c.union(c.descendants());
          const edges = inside.connectedEdges();
          c.descendants().addClass('lbl');
          edges.addClass('lbl');
          lit = inside.union(edges).union(edges.connectedNodes());
          lit = lit.union(lit.nodes().ancestors());
        }
      }
      if (state.selected) {
        const s = cy.getElementById(state.selected);
        if (s.nonempty()) {
          let nb = s.isNode() ? s.closedNeighborhood() : s.union(s.connectedNodes());
          nb = nb.union(nb.nodes().ancestors());
          nb.addClass('hl lbl');
          lit = lit ? lit.union(nb) : nb;
        }
      }
      if (lit) cy.elements().not(lit).addClass('faded');
      if (state.allLabels) cy.nodes('.code').addClass('lbl');
    });
  }

  function init(container, h) {
    handlers = h;
    cy = cytoscape({ container, style: STYLE, wheelSensitivity: 0.25, minZoom: 0.05, maxZoom: 4, boxSelectionEnabled: false });
    cy.on('tap', 'node', (ev) => {
      const n = ev.target;
      if (n.hasClass('component')) {
        focusComponent(n.id());
        handlers.onComponent?.(n.id());
      } else {
        state.selected = n.id();
        restyle();
        handlers.onNode?.(n.id());
      }
    });
    cy.on('tap', 'edge', (ev) => {
      state.selected = ev.target.id();
      restyle();
      handlers.onEdge?.(ev.target.data('raw'));
    });
    cy.on('tap', (ev) => {
      if (ev.target === cy) { state.selected = null; restyle(); handlers.onBackground?.(); }
    });
    cy.on('mouseover', 'node.code', (ev) => ev.target.addClass('lbl'));
    cy.on('mouseout', 'node.code', (ev) => { if (!state.allLabels) restyle(); });
    cy.on('dragfree', 'node', savePositions);
  }

  function render(data) {
    posKey = `cg.pos.${data.meta.project || 'default'}`;
    const { els, colors } = toElements(data);
    const incoming = new Map(els.map((e) => [e.data.id, e]));
    const first = cy.elements().empty();
    const fresh = [];
    cy.batch(() => {
      cy.elements().forEach((ele) => { if (!incoming.has(ele.id())) cy.remove(ele); });
      const saved = loadPositions();
      for (const e of els.filter((x) => x.group === 'nodes')) {
        const ele = cy.getElementById(e.data.id);
        if (ele.nonempty()) {
          if ((ele.data('parent') || undefined) !== e.data.parent) ele.move({ parent: e.data.parent ?? null });
          ele.data(e.data);
          ele.classes(e.classes);
        } else {
          const ele2 = cy.add({ ...e, position: saved[e.data.id] });
          if (!saved[e.data.id]) fresh.push(ele2);
        }
      }
      for (const e of els.filter((x) => x.group === 'edges')) {
        const ele = cy.getElementById(e.data.id);
        if (ele.nonempty()) { ele.data(e.data); } else { cy.add(e); }
      }
    });
    if (fresh.length === cy.nodes().length) {
      runLayout(true);
    } else if (fresh.length) {
      fresh.forEach((n) => {  // start new nodes next to their parent, then settle incrementally
        const p = n.parent();
        const at = p.nonempty() ? p.position() : { x: 0, y: 0 };
        n.position({ x: at.x + (Math.random() - 0.5) * 80, y: at.y + (Math.random() - 0.5) * 80 });
      });
      runLayout(false);
    } else if (first) {
      cy.fit(undefined, 40);
    }
    restyle();
    return colors;
  }

  function fitTo(eles) { cy.animate({ fit: { eles, padding: 50 }, duration: 450, easing: 'ease-in-out-cubic' }); }

  function focusComponent(id) {
    const c = cy.getElementById(id);
    if (c.empty()) return;
    state.focus = id;
    state.selected = null;
    restyle();
    fitTo(c.union(c.descendants()));
  }

  function selectNode(id, { zoom = true } = {}) {
    const n = cy.getElementById(id);
    if (n.empty()) return;
    if (n.hasClass('component')) { focusComponent(id); return; }
    state.focus = n.data('component') !== id ? n.data('component') : state.focus;
    state.selected = id;
    cy.elements().unselect();
    n.select();
    restyle();
    if (zoom) cy.animate({ center: { eles: n }, zoom: Math.max(cy.zoom(), 1.5), duration: 450 });
  }

  function selectEdge(id) {
    const e = cy.getElementById(`e${id}`);
    if (e.empty()) return;
    state.selected = e.id();
    cy.elements().unselect();
    e.select();
    restyle();
    fitTo(e.union(e.connectedNodes()));
  }

  function reset() {
    state.focus = null;
    state.selected = null;
    cy.elements().unselect();
    restyle();
    fitTo(cy.elements(':visible'));
  }

  function setAllLabels(on) { state.allLabels = on; restyle(); }

  function applyFilters(f) {
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        const d = n.data();
        const hidden = !f.layers.has(d.layer) || !f.types.has(d.type) || (d.type !== 'COMPONENT' && !f.statuses.has(d.status));
        n.toggleClass('filtered', hidden);
      });
      cy.edges().forEach((e) => e.toggleClass('filtered', !f.edges.has(e.data('kind'))));
    });
  }

  function relayout() { runLayout(true); }
  function resize() { cy?.resize(); }

  return { init, render, focusComponent, selectNode, selectEdge, reset, setAllLabels, applyFilters, relayout, resize, state };
})();
