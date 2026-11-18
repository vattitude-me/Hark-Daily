import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// web/js is CommonJS to Node here (root package.json), so load .mjs copies like the other tests do.
const read = (p) => readFileSync(new URL(`../../web/js/${p}`, import.meta.url), 'utf8');
const dir = mkdtempSync(join(tmpdir(), 'slow-net-'));
writeFileSync(join(dir, 'network.js'), read('network.js'));
writeFileSync(join(dir, 'config.mjs'), "export const SUPABASE_URL = 'https://x'; export const SUPABASE_PUBLISHABLE_KEY = 'k';");
writeFileSync(join(dir, 'api.mjs'), read('api.js').replace("'../config.js'", "'./config.mjs'"));
writeFileSync(join(dir, 'storypack.mjs'), read('storypack.js').replace("'./api.js'", "'./api.mjs'").replace("'../config.js'", "'./config.mjs'"));
writeFileSync(join(dir, 'player.mjs'), read('player.js').replace("'./api.js'", "'./api.mjs'").replace("'./storypack.js'", "'./storypack.mjs'"));

const net = await import(join(dir, 'network.js'));
const api = await import(join(dir, 'api.mjs'));
const { Player } = await import(join(dir, 'player.mjs'));

function setNav(value) {
  Object.defineProperty(globalThis, 'navigator', { value, configurable: true, writable: true });
}

// ---- banner decisions ----

test('bannerAction: "back online" only follows offline, never a slow patch', () => {
  assert.equal(net.bannerAction('ok', 'offline').back, true);
  assert.equal(net.bannerAction('ok', 'slow').back, false);
  assert.equal(net.bannerAction('ok', null).back, false);
  assert.equal(net.bannerAction('ok', 'offline').show, false);
});

test('bannerAction: offline stays up, slow hides itself', () => {
  const off = net.bannerAction('offline', 'ok');
  assert.equal(off.show, true);
  assert.equal(off.autoHideMs, 0);
  const slow = net.bannerAction('slow', 'ok', { now: 1_000_000 });
  assert.equal(slow.show, true);
  assert.ok(slow.autoHideMs > 0);
});

test('bannerAction: slow banner does not come back within the cooldown', () => {
  const now = 10_000_000;
  assert.equal(net.bannerAction('slow', 'ok', { now, lastSlowAt: now - 30_000 }).show, false);
  assert.equal(net.bannerAction('slow', 'ok', { now, lastSlowAt: now - 3 * 60_000 }).show, true);
});

// ---- clip retries ----

class MockAudio extends EventTarget {
  constructor() {
    super();
    this.currentTime = 0;
    this.paused = true;
    this.readyState = 0;
    this.error = null;
  }
  play() { this.paused = false; return Promise.resolve(); }
  pause() { this.paused = true; }
  load() {}
  removeAttribute() {}
}

function makePlayer() {
  const audio = new MockAudio();
  const player = new Player({ audio, preloader: new MockAudio(), el: {} });
  player.clips = [{ start: 0, end: 30, url: 'a.mp3' }, { start: 30, end: 60, url: 'b.mp3' }];
  player.index = 0;
  player.wantsPlay = true;
  player.setPlaying = () => {}; // DOM and wake-lock side effects are out of scope here
  player.tick = () => {};
  player.setupAudioElement(audio);
  const loads = [];
  player.loadClip = (i, opts) => { loads.push({ i, ...opts }); };
  return { player, audio, loads };
}

test('retryClip: keeps the original position across attempts and gives up after three', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  setNav({ onLine: true });
  const { player, audio, loads } = makePlayer();
  audio.currentTime = 12.5;
  player.retryClip();
  t.mock.timers.tick(1500);
  assert.equal(loads.length, 1);
  assert.equal(loads[0].seek, 12.5);
  assert.equal(loads[0].autoplay, true);

  audio.currentTime = 0; // a failed reload reads 0
  player.retryClip();
  t.mock.timers.tick(3000);
  player.retryClip();
  t.mock.timers.tick(6000);
  assert.equal(loads.length, 3);
  assert.ok(loads.every((l) => l.seek === 12.5), 'every retry resumes at the first failure point');

  player.retryClip(); // fourth failure: stop
  t.mock.timers.tick(20000);
  assert.equal(loads.length, 3);
  assert.equal(player.wantsPlay, false);
  assert.equal(player.retry, null);
  net.noteOk();
});

test('retryClip: audio that plays resets the retry budget', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  setNav({ onLine: true });
  const { player, audio, loads } = makePlayer();
  player.retryClip();
  player.retryClip();
  assert.equal(player.retry.count, 2);
  audio.dispatchEvent(new Event('playing'));
  assert.equal(player.retry, null);
  player.retryClip();
  assert.equal(player.retry.count, 1);
  t.mock.timers.tick(1500);
  assert.equal(loads.length, 1);
  net.noteOk();
});

test('retryClip: offline waits for one "online" event and does not spend attempts', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  setNav({ onLine: false });
  const win = new EventTarget();
  let added = 0;
  const realAdd = win.addEventListener.bind(win);
  win.addEventListener = (type, fn, opts) => { if (type === 'online') added += 1; realAdd(type, fn, opts); };
  globalThis.window = win;
  try {
    const { player, loads } = makePlayer();
    player.retryClip();
    player.retryClip();
    player.retryClip();
    assert.equal(added, 1, 'only one online listener is ever pending');
    assert.equal(player.retry.count, 0);
    assert.equal(loads.length, 0);
    setNav({ onLine: true });
    win.dispatchEvent(new Event('online'));
    assert.equal(loads.length, 1);
  } finally {
    delete globalThis.window;
    setNav({ onLine: true });
  }
});

test('retryClip: a retry for a clip the listener left is dropped', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  setNav({ onLine: true });
  const { player, loads } = makePlayer();
  player.retryClip();
  player.index = 1;
  t.mock.timers.tick(5000);
  assert.equal(loads.length, 0);
  net.noteOk();
});

test('pause from a load error keeps the play intent, a user pause clears it', () => {
  const { player, audio } = makePlayer();
  audio.error = { code: 2 };
  audio.dispatchEvent(new Event('pause'));
  assert.equal(player.wantsPlay, true);
  audio.error = null;
  audio.dispatchEvent(new Event('pause'));
  assert.equal(player.wantsPlay, false);
});

// ---- pack fetch ----

const pack = (tag) => ({ briefing: { date: '2026-11-18' }, story_audio: [], tag });
const reply = (body, status = 200) => ({ ok: status === 200, json: async () => body });

test('firstPack: falls through to the next URL when one fails', async () => {
  setNav({ onLine: true });
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => (url === 'a' ? reply(null, 404) : reply(pack(url)));
  try {
    const got = await api.firstPack(['a', 'b', 'c']);
    assert.equal(got.tag, 'b');
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('firstPack: a slow first URL starts the next, keeps priority, and cancels the spare', async () => {
  setNav({ onLine: true });
  const realFetch = globalThis.fetch;
  const started = [];
  const signals = {};
  globalThis.fetch = (url, { signal } = {}) => {
    started.push(url);
    signals[url] = signal;
    const ms = url === 'a' ? 60 : 5;
    return new Promise((resolve, reject) => {
      const t = setTimeout(() => resolve(reply(pack(url))), ms);
      signal?.addEventListener('abort', () => { clearTimeout(t); reject(new Error('aborted')); });
    });
  };
  try {
    const got = await api.firstPack(['a', 'b', 'c'], { hedgeMs: 10 });
    assert.equal(got.tag, 'a', 'today\'s pack wins over a faster fallback');
    assert.ok(started.includes('b'), 'the fallback was started while the first was slow');
    assert.equal(net.isSlow(), false, 'cancelling the spare is not a slow signal');
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('publicPack: concurrent callers share one download', async () => {
  setNav({ onLine: true });
  const realFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; await new Promise((r) => setTimeout(r, 5)); return reply(pack('x')); };
  try {
    const [a, b] = await Promise.all([api.publicPack('2026-11-18'), api.publicPack('2026-11-18')]);
    assert.equal(a, b);
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = realFetch;
  }
});
