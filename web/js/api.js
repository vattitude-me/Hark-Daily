// Thin wrapper around the JSON API.
async function request(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON error page */ }
  if (!res.ok) {
    let msg = data?.detail;
    if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join(', ');
    throw new Error(msg || `Request failed (${res.status})`);
  }
  return data;
}

export const api = {
  latest: () => request('/api/briefing/latest'),
  briefing: (day) => request(`/api/briefing/${encodeURIComponent(day)}`),
  archive: () => request('/api/briefings'),
  generate: () => request('/api/briefing/generate', { method: 'POST' }),
  status: () => request('/api/status'),
  sources: () => request('/api/sources'),
  detectSource: (url) => request('/api/sources/detect', { method: 'POST', body: { url } }),
  addSource: (body) => request('/api/sources', { method: 'POST', body }),
  updateSource: (id, body) => request(`/api/sources/${id}`, { method: 'PATCH', body }),
  deleteSource: (id) => request(`/api/sources/${id}`, { method: 'DELETE' }),
  voices: () => request('/api/voices'),
  settings: () => request('/api/settings'),
  saveSettings: (body) => request('/api/settings', { method: 'PUT', body }),
  previewUrl: (voice, speed) => `/api/voices/preview?voice=${encodeURIComponent(voice)}&speed=${speed}`,
};

// Tiny DOM helper: h('div', {class: 'x', onclick}, child, 'text')
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.className = v;
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k === 'html') el.innerHTML = v; // only ever used with static markup
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export const icon = (name, cls = '') => {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  if (cls) svg.setAttribute('class', cls);
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
};

export const fmtTime = (s) => {
  if (!Number.isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
};

export function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 3600) return `${Math.max(1, Math.round(diff / 60))}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return new Date(iso).toLocaleDateString('en-CA', { month: 'short', day: 'numeric' });
}

export const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem(`mb-${key}`); return v == null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(`mb-${key}`, JSON.stringify(value)); } catch { /* storage unavailable */ }
  },
};

let toastTimer;
export function toast(message, { error = false, ms = 3500 } = {}) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.classList.toggle('error', error);
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), ms);
}
