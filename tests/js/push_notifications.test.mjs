import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const require = createRequire(import.meta.url);

function createMemoryStorage() {
  const map = new Map();
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => { map.set(k, String(v)); },
    removeItem: (k) => { map.delete(k); },
    clear: () => { map.clear(); },
  };
}

function makeElement(id = '') {
  const attrs = new Map();
  const classes = new Set();
  const listeners = new Map();
  const children = [];
  let rawText = '';
  const el = {
    id,
    children,
    innerHTML: '',
    value: '',
    dataset: {},
    style: { setProperty() {}, removeProperty() {} },
    get textContent() {
      return children.length ? children.map((c) => c.textContent || '').join('') : rawText;
    },
    set textContent(v) {
      children.length = 0;
      rawText = String(v ?? '');
    },
    get className() {
      return Array.from(classes).join(' ');
    },
    set className(v) {
      classes.clear();
      for (const c of String(v || '').split(/\s+/).filter(Boolean)) classes.add(c);
    },
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      toggle: (c, force) => {
        if (force === undefined ? !classes.has(c) : force) classes.add(c);
        else classes.delete(c);
      },
      contains: (c) => classes.has(c),
    },
    replaceChildren: (...kids) => {
      children.length = 0;
      children.push(...kids);
    },
    append: (...kids) => {
      children.push(...kids);
    },
    setAttribute: (k, v) => attrs.set(k, String(v)),
    getAttribute: (k) => (attrs.has(k) ? attrs.get(k) : null),
    removeAttribute: (k) => attrs.delete(k),
    addEventListener: (evt, fn) => {
      const list = listeners.get(evt) || [];
      list.push(fn);
      listeners.set(evt, list);
    },
    removeEventListener: () => {},
    querySelectorAll: () => [],
    querySelector: () => null,
    dispatch: (evt) => (listeners.get(evt) || []).forEach((fn) => fn()),
  };
  return el;
}

function buildSandbox({ fetchImpl }) {
  const dir = mkdtempSync(join(tmpdir(), 'hark-push-test-'));
  const origSetTimeout = globalThis.setTimeout;
  const origSetInterval = globalThis.setInterval;
  const timers = new Set();
  const intervals = new Set();
  globalThis.setTimeout = (fn, ms, ...args) => {
    const id = origSetTimeout(fn, ms, ...args);
    timers.add(id);
    id?.unref?.();
    return id;
  };
  globalThis.setInterval = (fn, ms, ...args) => {
    const id = origSetInterval(fn, ms, ...args);
    intervals.add(id);
    id?.unref?.();
    return id;
  };
  const cleanupTimers = () => {
    for (const id of timers) clearTimeout(id);
    for (const id of intervals) clearInterval(id);
    timers.clear();
    intervals.clear();
    globalThis.setTimeout = origSetTimeout;
    globalThis.setInterval = origSetInterval;
  };

  const elements = new Map();
  const getEl = (id) => {
    if (!elements.has(id)) elements.set(id, makeElement(id));
    return elements.get(id);
  };
  // Pre-seed key DOM nodes inspected by toggleMorningAlerts and toast()
  const menuPushBtn = getEl('menuPushBtn');
  menuPushBtn.setAttribute('aria-checked', 'false');
  const toastEl = getEl('toast');

  const storage = createMemoryStorage();
  globalThis.self = globalThis;
  globalThis.localStorage = storage;
  globalThis.sessionStorage = createMemoryStorage();
  globalThis.fetch = fetchImpl;
  globalThis.window = {
    location: {
      href: 'https://hark.vattitude.ca/',
      origin: 'https://hark.vattitude.ca',
      hostname: 'hark.vattitude.ca',
      search: '',
      hash: '',
      pathname: '/',
    },
    addEventListener: () => {},
    removeEventListener: () => {},
    matchMedia: () => ({ matches: false }),
    PushManager: function PushManager() {},
    isSecureContext: true,
  };
  globalThis.location = globalThis.window.location;
  globalThis.document = {
    currentScript: { tagName: 'SCRIPT', src: 'https://hark.vattitude.ca/js/vendor/supabase.min.js' },
    visibilityState: 'visible',
    readyState: 'complete',
    body: makeElement('body'),
    documentElement: makeElement('html'),
    getElementById: (id) => getEl(id),
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: () => {},
    removeEventListener: () => {},
    createElement: (tag) => makeElement(tag),
  };
  Object.defineProperty(globalThis, 'navigator', {
    value: { userAgent: 'Mozilla/5.0 Chrome/126.0', serviceWorker: null, onLine: true },
    configurable: true,
    writable: true,
  });

  // Load actual bundled supabase-js so PostgREST request headers/URLs match production
  globalThis.supabase = require('../../web/js/vendor/supabase.min.js');
  globalThis.window.supabase = globalThis.supabase;

  writeFileSync(join(dir, 'config.mjs'), readFileSync(new URL('../../web/config.js', import.meta.url), 'utf8'));
  writeFileSync(join(dir, 'network.mjs'), readFileSync(new URL('../../web/js/network.js', import.meta.url), 'utf8'));
  writeFileSync(
    join(dir, 'api.mjs'),
    readFileSync(new URL('../../web/js/api.js', import.meta.url), 'utf8')
      .replace("'../config.js'", "'./config.mjs'")
      .replace("'./network.js'", "'./network.mjs'")
  );
  writeFileSync(
    join(dir, 'sheets.mjs'),
    readFileSync(new URL('../../web/js/sheets.js', import.meta.url), 'utf8')
      .replace("'./api.js'", "'./api.mjs'")
      .replace("'../config.js'", "'./config.mjs'")
  );
  writeFileSync(join(dir, 'player.mjs'), 'export class Player {}; export const posKeyFor = () => ""; export const safeExternalUrl = (u) => u;');
  writeFileSync(join(dir, 'landing.mjs'), 'export class Landing {};');
  writeFileSync(join(dir, 'pages.mjs'), 'export class SourcesPage {}; export class SettingsPage {}; export class AdminPage {};');
  writeFileSync(join(dir, 'storypack.mjs'), 'export const buildBriefing = () => ({}); export const formatGeneratedPeriod = () => ""; export const READY_KEY = "ready"; export const storyKey = () => ""; export const titlesMatch = () => false;');
  writeFileSync(join(dir, 'design.mjs'), 'export const applyPhotoMode = () => {};');

  const appSrc = readFileSync(new URL('../../web/js/app.js', import.meta.url), 'utf8')
    .replace("'./api.js'", "'./api.mjs'")
    .replace("'./network.js'", "'./network.mjs'")
    .replace("'./player.js'", "'./player.mjs'")
    .replace("'./landing.js'", "'./landing.mjs'")
    .replace("'./sheets.js'", "'./sheets.mjs'")
    .replace("'./pages/sources.js'", "'./pages.mjs'")
    .replace("'./pages/settings.js'", "'./pages.mjs'")
    .replace("'./pages/admin.js'", "'./pages.mjs'")
    .replace("'./storypack.js'", "'./storypack.mjs'")
    .replace("'./design.js'", "'./design.mjs'")
    .replace("'../config.js'", "'./config.mjs'");
  writeFileSync(join(dir, 'app.mjs'), appSrc);

  return { dir, storage, menuPushBtn, toastEl, cleanupTimers };
}

function makeFakeSub(endpoint = 'https://fcm.googleapis.com/fcm/send/test-sub-1', appKeyBytes = null) {
  const bytes = appKeyBytes || new Uint8Array([
    4, ...Array.from({ length: 64 }, (_, i) => (i + 1) & 0xff),
  ]);
  return {
    endpoint,
    options: { applicationServerKey: bytes.buffer },
    unsubscribed: false,
    toJSON() {
      return {
        endpoint: this.endpoint,
        keys: { p256dh: 'BTestP256dhKeyValue1234567890', auth: 'AuthSecret123456' },
      };
    },
    async unsubscribe() {
      this.unsubscribed = true;
      return true;
    },
  };
}

test('toast CSS sits cleanly above drawer, sheets, and modals', () => {
  const css = readFileSync(new URL('../../web/css/styles.css', import.meta.url), 'utf8');
  const toastBlock = css.match(/\.toast\s*\{[^}]*\}/);
  assert.ok(toastBlock, '.toast rule must exist');
  const zMatch = toastBlock[0].match(/z-index:\s*(\d+)/);
  assert.ok(zMatch, '.toast must set z-index');
  const toastZ = Number(zMatch[1]);
  assert.ok(toastZ > 1200, `Expected .toast z-index (${toastZ}) to sit above drawers (1000) and modals/save-bar (1200)`);
});

test('api.pushSubscribe uses plain insert (no ON CONFLICT) and treats duplicate 23505 as success', async () => {
  const requests = [];
  let mode = 'insert-ok';
  const fetchSpy = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    const method = init.method || (typeof input === 'object' && input.method) || 'GET';
    const hdrs = {};
    const h = init.headers || (typeof input === 'object' && input.headers);
    if (h && typeof h.forEach === 'function') h.forEach((v, k) => { hdrs[k.toLowerCase()] = v; });
    else if (h) for (const [k, v] of Object.entries(h)) hdrs[k.toLowerCase()] = v;
    requests.push({ url, method, headers: hdrs, body: init.body });

    if (url.includes('/rest/v1/push_subscriptions')) {
      if (mode === 'insert-ok') {
        return new Response(null, { status: 201 });
      }
      if (mode === 'duplicate-23505') {
        return new Response(
          JSON.stringify({ code: '23505', details: null, hint: null, message: 'duplicate key value violates unique constraint' }),
          { status: 409, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (mode === 'rls-42501') {
        return new Response(
          JSON.stringify({ code: '42501', details: null, hint: null, message: 'permission denied for table push_subscriptions' }),
          { status: 401, headers: { 'Content-Type': 'application/json' } }
        );
      }
    }
    if (url.includes('/rest/v1/rpc/get_vapid_public_key')) {
      return new Response(JSON.stringify('BPPMMoo2qFby_GY6cY4Gbk0r7EVSIUMetWaADc-IaM2rfp5ad8l_SwzEOszN-IZNJgfLrYpjcHa-Dt9LEac2aS0'), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };

  const { dir, cleanupTimers } = buildSandbox({ fetchImpl: fetchSpy });
  let sbRef = null;
  try {
    const { api, sb } = await import(join(dir, 'api.mjs'));
    sbRef = sb;
    const fakeSubJson = makeFakeSub().toJSON();

    // 1. Fresh guest subscription insert
    const ok = await api.pushSubscribe(fakeSubJson);
    assert.equal(ok, true);
    const pushReq = requests.find((r) => r.url.includes('/rest/v1/push_subscriptions'));
    assert.ok(pushReq, 'Must POST to push_subscriptions');
    assert.equal(pushReq.method, 'POST');
    assert.ok(!pushReq.url.includes('on_conflict='), 'Must NOT use on_conflict (ON CONFLICT requires SELECT for anon)');
    assert.ok(!(pushReq.headers.prefer || '').includes('ignore-duplicates'), 'Must NOT send resolution=ignore-duplicates');
    assert.deepEqual(JSON.parse(pushReq.body), {
      endpoint: fakeSubJson.endpoint,
      p256dh: fakeSubJson.keys.p256dh,
      auth: fakeSubJson.keys.auth,
      user_id: null,
    });

    // 2. Duplicate endpoint (23505) returns true instead of throwing
    mode = 'duplicate-23505';
    assert.equal(await api.pushSubscribe(fakeSubJson), true);

    // 3. Other Postgres errors surface cleanly
    mode = 'rls-42501';
    await assert.rejects(() => api.pushSubscribe(fakeSubJson), /permission denied/);

    // 4. Invalid subscription payload rejects cleanly
    await assert.rejects(() => api.pushSubscribe({ endpoint: 'https://x', keys: {} }), /valid push subscription/);

    // 5. Guest vapidPublicKey resolves via RPC when app_status returns empty
    assert.equal(
      await api.vapidPublicKey(),
      'BPPMMoo2qFby_GY6cY4Gbk0r7EVSIUMetWaADc-IaM2rfp5ad8l_SwzEOszN-IZNJgfLrYpjcHa-Dt9LEac2aS0'
    );
  } finally {
    sbRef?.auth?.stopAutoRefresh?.();
    sbRef?.auth?.broadcastChannel?.close?.();
    cleanupTimers();
    rmSync(dir, { recursive: true, force: true });
  }
});

test('toggleMorningAlerts handles guest opt-in, permission denial, unsupported browser, opt-out, and concurrent taps', async () => {
  const validVapid = 'BPPMMoo2qFby_GY6cY4Gbk0r7EVSIUMetWaADc-IaM2rfp5ad8l_SwzEOszN-IZNJgfLrYpjcHa-Dt9LEac2aS0';
  const postedBodies = [];
  const fetchSpy = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    if (url.includes('/rest/v1/rpc/get_vapid_public_key')) {
      return new Response(JSON.stringify(validVapid), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (url.includes('/rest/v1/push_subscriptions')) {
      postedBodies.push(JSON.parse(init.body || '{}'));
      return new Response(null, { status: 201 });
    }
    return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };

  const { dir, storage, menuPushBtn, toastEl, cleanupTimers } = buildSandbox({ fetchImpl: fetchSpy });
  let sbRef = null;
  try {
    let activeSub = null;
    let subscribeCalls = 0;
    const reg = {
      pushManager: {
        getSubscription: async () => activeSub,
        subscribe: async () => {
          subscribeCalls += 1;
          activeSub = makeFakeSub();
          return activeSub;
        },
      },
    };
    globalThis.navigator.serviceWorker = { ready: Promise.resolve(reg) };
    globalThis.Notification = {
      permission: 'default',
      requestPermission: async () => {
        globalThis.Notification.permission = 'granted';
        return 'granted';
      },
    };

    const suffix = Date.now();
    const { sb } = await import(`${join(dir, 'api.mjs')}`);
    sbRef = sb;
    await import(`${join(dir, 'app.mjs')}?t=${suffix}`);
    const { toggleMorningAlerts, isPushEnabled } = globalThis.window;

    // 1. Concurrent taps while toggling ON should only subscribe once
    await Promise.all([toggleMorningAlerts(), toggleMorningAlerts()]);
    assert.equal(subscribeCalls, 1, 'In-flight guard must prevent duplicate subscribe calls');
    assert.equal(postedBodies.length, 1, 'Guest push subscription must be POSTed to Supabase');
    assert.equal(postedBodies[0].user_id, null);
    assert.equal(storage.getItem('hark_push_registered'), 'true');
    assert.equal(storage.getItem('hark_morning_alerts_disabled'), null);
    assert.equal(menuPushBtn.getAttribute('aria-checked'), 'true');
    assert.equal(menuPushBtn.getAttribute('aria-busy'), null);
    assert.equal(isPushEnabled(), true);
    assert.match(toastEl.textContent, /Morning alerts enabled/);

    // 2. Toggling OFF unsubscribes and resets state
    await toggleMorningAlerts();
    assert.equal(activeSub.unsubscribed, true);
    assert.equal(storage.getItem('hark_morning_alerts_disabled'), 'true');
    assert.equal(storage.getItem('hark_push_registered'), null);
    assert.equal(menuPushBtn.getAttribute('aria-checked'), 'false');
    assert.equal(isPushEnabled(), false);

    // 3. Denied browser permission surfaces clear error toast and keeps toggle off
    globalThis.Notification.permission = 'denied';
    await toggleMorningAlerts();
    assert.equal(menuPushBtn.getAttribute('aria-checked'), 'false');
    assert.match(toastEl.textContent, /blocked — allow them in browser site settings/);
    assert.ok(toastEl.classList.contains('toast-error'));

    // 4. Unsupported context (e.g. non-installed iOS Safari) gives actionable Home Screen toast
    globalThis.Notification.permission = 'default';
    delete globalThis.window.PushManager;
    Object.defineProperty(globalThis.navigator, 'userAgent', { value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)', configurable: true });
    await toggleMorningAlerts();
    assert.equal(menuPushBtn.getAttribute('aria-checked'), 'false');
    assert.match(toastEl.textContent, /Home Screen/);
  } finally {
    sbRef?.auth?.stopAutoRefresh?.();
    sbRef?.auth?.broadcastChannel?.close?.();
    cleanupTimers();
    delete globalThis.Notification;
    rmSync(dir, { recursive: true, force: true });
  }
});
