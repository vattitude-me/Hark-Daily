import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// web/js is CommonJS to Node here (root package.json), so load a .mjs copy like the other tests do.
const dir = mkdtempSync(join(tmpdir(), 'network-test-'));
writeFileSync(join(dir, 'network.mjs'), readFileSync(new URL('../../web/js/network.js', import.meta.url)));
const net = await import(join(dir, 'network.mjs'));

function setNav(value) {
  Object.defineProperty(globalThis, 'navigator', { value, configurable: true, writable: true });
}

test('classify: wifi-class connection is ok', () => {
  assert.equal(net.classify({ connection: { effectiveType: '4g', downlink: 10, rtt: 50 } }), 'ok');
});

test('classify: offline wins over everything', () => {
  assert.equal(net.classify({ onLine: false, connection: { effectiveType: '4g' }, observed: 5 }), 'offline');
});

test('classify: connection estimates never reach the listener', () => {
  // Chrome reports ~1.5 Mbps downlink on fast Wi-Fi while audio streams. That must not read as slow.
  assert.equal(net.classify({ connection: { effectiveType: '4g', downlink: 1.4, rtt: 50 } }), 'ok');
  assert.equal(net.classify({ connection: { effectiveType: '3g' } }), 'ok');
});

test('weakHint: 3G, save-data, low downlink and high rtt tune timeouts', () => {
  assert.equal(net.weakHint({ effectiveType: '3g' }), true);
  assert.equal(net.weakHint({ effectiveType: '4g', saveData: true }), true);
  assert.equal(net.weakHint({ effectiveType: '4g', downlink: 0.8 }), true);
  assert.equal(net.weakHint({ effectiveType: '4g', downlink: 5, rtt: 600 }), true);
  assert.equal(net.weakHint({ effectiveType: '4g', downlink: 10, rtt: 50 }), false);
  assert.equal(net.weakHint(null), false);
});

test('a downlink dip on Wi-Fi stretches timeouts but shows nothing', () => {
  setNav({ onLine: true, connection: { effectiveType: '4g', downlink: 1.4, rtt: 50 } });
  net.noteOk();
  assert.equal(net.quality(), 'ok');
  assert.equal(net.isSlow(), true);
  assert.equal(net.timeoutFor(4000), 12000);
  setNav({ onLine: true, connection: null });
});

test('a long buffering wait marks the link slow on its own', () => {
  assert.equal(net.classify({ stalled: true }), 'slow');
  setNav({ onLine: true, connection: null });
  net.noteOk();
  net.noteStall();
  assert.equal(net.quality(), 'slow');
  net.noteOk();
  assert.equal(net.quality(), 'ok');
});

test('classify: two stalls or timeouts mark a link slow, one does not', () => {
  assert.equal(net.classify({ observed: 1 }), 'ok');
  assert.equal(net.classify({ observed: 2 }), 'slow');
});

test('observed events flip quality and noteOk clears them', () => {
  setNav({ onLine: true, connection: { effectiveType: '4g', downlink: 10, rtt: 50 } });
  net.noteOk();
  assert.equal(net.quality(), 'ok');
  const seen = [];
  const off = net.onChange((q) => seen.push(q));
  net.noteSlow();
  assert.equal(net.quality(), 'ok');
  net.noteSlow();
  assert.equal(net.quality(), 'slow');
  net.noteOk();
  assert.equal(net.quality(), 'ok');
  off();
  assert.deepEqual(seen.slice(-2), ['slow', 'ok']);
});

test('timeoutFor stretches on slow links and fails fast offline', () => {
  setNav({ onLine: true, connection: { effectiveType: '4g', downlink: 10, rtt: 50 } });
  net.noteOk();
  assert.equal(net.timeoutFor(4000), 4000);
  setNav({ onLine: true, connection: { effectiveType: '3g' } });
  net.noteOk();
  assert.equal(net.timeoutFor(4000), 12000);
  setNav({ onLine: false });
  assert.equal(net.timeoutFor(8000), 1500);
  setNav({ onLine: true, connection: null });
});

test('player and app are wired to the network module', () => {
  const player = readFileSync(new URL('../../web/js/player.js', import.meta.url), 'utf8');
  assert.match(player, /from '\.\/network\.js'/);
  for (const ev of ['waiting', 'stalled', 'playing']) assert.ok(player.includes(`addEventListener('${ev}'`), ev);
  assert.ok(player.includes('retryClip()'));
  const app = readFileSync(new URL('../../web/js/app.js', import.meta.url), 'utf8');
  assert.ok(app.includes('initNetwork(toast)'));
  assert.ok(app.includes('timeoutFor(ms)'));
  const sw = readFileSync(new URL('../../web/sw.js', import.meta.url), 'utf8');
  assert.ok(sw.includes("'/js/network.js'"), 'service worker must precache network.js');
  assert.ok(sw.includes("cache: 'reload'"), 'precache must bypass the HTTP cache');
  assert.ok(sw.includes('networkFirst('), 'code must be network-first so a deploy takes effect');
});

test('boot splash waits for the app and offers a retry instead of an empty page', () => {
  const html = readFileSync(new URL('../../web/index.html', import.meta.url), 'utf8');
  assert.ok(html.includes('id="splashMsg"') && html.includes('id="splashRetry"'));
  assert.ok(html.includes('window.__harkBooted'), 'splash must key off the app having started');
  assert.ok(!html.includes('}, 2200);'), 'splash must not be dismissed on a blind timer');
  const app = readFileSync(new URL('../../web/js/app.js', import.meta.url), 'utf8');
  assert.ok(app.includes('window.__harkBooted = true'));
});

test('withTimeout only reports slow when the timeout wins, not when the request finishes in time', () => {
  const app = readFileSync(new URL('../../web/js/app.js', import.meta.url), 'utf8');
  assert.ok(app.includes('clearTimeout(timer)'), 'the timer must be cleared once the request settles');
});
