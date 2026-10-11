/* Visual vocabulary: one place mapping domain values to colors and shapes. */
window.CG = window.CG || {};

CG.theme = {
  statusOrder: ['PLANNED', 'IN_PROGRESS', 'COMPLETED', 'TESTED', 'EVALUATED'],
  status: {
    PLANNED: '#6b7280', IN_PROGRESS: '#f59e0b', COMPLETED: '#3b82f6', TESTED: '#06b6d4', EVALUATED: '#22c55e',
  },
  types: {
    COMPONENT: { shape: 'round-rectangle', label: 'Component (C4 boundary)' },
    SERVICE_CLASS: { shape: 'hexagon', label: 'Service class' },
    CLASS: { shape: 'round-rectangle', label: 'Class' },
    INTERFACE: { shape: 'ellipse', label: 'Interface' },
    UTILITY_CLASS: { shape: 'diamond', label: 'Utility class' },
    CONFIG_CLASS: { shape: 'cut-rectangle', label: 'Config class' },
  },
  edges: {
    CALLS: { color: '#60a5fa', label: 'CALLS (function contract)' },
    DEPENDS: { color: '#c084fc', label: 'DEPENDS (same level)' },
    IMPLEMENTS: { color: '#9ca3af', label: 'IMPLEMENTS (interface)' },
    USES: { color: '#6b7280', label: 'USES (shared type)' },
  },
  layers: { PLATFORM: 'Platform (solid boundary)', USECASE: 'Use case (dashed boundary)' },
  verdict: { PASS: '#22c55e', FAIL: '#ef4444', WAIVED: '#9ca3af' },
  task: { OPEN: '#6b7280', IN_PROGRESS: '#f59e0b', BLOCKED: '#ef4444', DONE: '#22c55e', CANCELLED: '#4b5563' },
  adr: { PROPOSED: '#f59e0b', ACCEPTED: '#22c55e', REJECTED: '#ef4444', SUPERSEDED: '#6b7280' },
  palette: ['#38bdf8', '#f472b6', '#a3e635', '#facc15', '#c084fc', '#fb7185', '#2dd4bf', '#fdba74', '#a5b4fc', '#e879f9',
    '#4ade80', '#fca5a5'],

  pill(text, color) {
    return `<span class="pill" style="color:${color};border-color:${color}55;background:${color}1a">${CG.esc(text)}</span>`;
  },

  shapeSvg(type, color = '#9ca3af') {
    const shapes = {
      'round-rectangle': '<rect x="1" y="2" width="12" height="10" rx="3"/>',
      hexagon: '<polygon points="3.5,1.5 10.5,1.5 13.5,7 10.5,12.5 3.5,12.5 0.5,7"/>',
      ellipse: '<circle cx="7" cy="7" r="5.5"/>',
      diamond: '<polygon points="7,0.5 13.5,7 7,13.5 0.5,7"/>',
      'cut-rectangle': '<polygon points="4,1.5 10,1.5 13,4.5 13,9.5 10,12.5 4,12.5 1,9.5 1,4.5"/>',
    };
    const t = this.types[type] || this.types.CLASS;
    return `<svg class="shape" viewBox="0 0 14 14" fill="${color}">${shapes[t.shape]}</svg>`;
  },
};
