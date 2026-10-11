/* HTTP client + small DOM helpers shared by all UI modules. */
window.CG = window.CG || {};

CG.api = {
  async request(method, path, body, actor) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    if (actor) opts.headers['X-Actor'] = actor;
    const res = await fetch('/api' + path, opts);
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(json.message || res.statusText);
      err.body = json;
      throw err;
    }
    return json;
  },
  get(path) { return this.request('GET', path); },
  post(path, body, actor = 'human') { return this.request('POST', path, body, actor); },
};

CG.esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

CG.fmtDate = (iso) => (iso ? iso.replace('T', ' ').replace('+00:00', 'Z') : '');

CG.toast = (msg) => {
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 5000);
};
