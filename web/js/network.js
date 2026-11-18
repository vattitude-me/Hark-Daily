// Connection awareness for weak mobile networks (low 4G, 3G, patchy coverage).
//
// Wi-Fi needs none of this. On a weak link we do three things: stretch request timeouts so a slow
// download is not abandoned half way, hold back background preloading so it does not starve the clip
// that is playing, and tell the listener what is going on instead of failing silently.
//
// This module imports nothing from the app so it can be tested on its own.

const SLOW_TYPES = new Set(['slow-2g', '2g', '3g']);
const SLOW_DOWNLINK_MBPS = 1.5;
const SLOW_RTT_MS = 450;
const OBSERVED_WINDOW_MS = 2 * 60 * 1000;
const OBSERVED_THRESHOLD = 2;
const SLOW_TIMEOUT_FACTOR = 3;

/** Pure classifier. `observed` is the number of stalls or timeouts seen in the last two minutes. */
export function classify({ onLine = true, connection = null, observed = 0 } = {}) {
  if (onLine === false) return 'offline';
  if (observed >= OBSERVED_THRESHOLD) return 'slow';
  if (connection) {
    if (connection.saveData) return 'slow';
    if (SLOW_TYPES.has(connection.effectiveType)) return 'slow';
    // "4g" is reported for any link that clears a low bar, so also read the measured numbers.
    if (typeof connection.downlink === 'number' && connection.downlink > 0 && connection.downlink < SLOW_DOWNLINK_MBPS) return 'slow';
    if (typeof connection.rtt === 'number' && connection.rtt > SLOW_RTT_MS) return 'slow';
  }
  return 'ok';
}

const hasNav = () => typeof navigator !== 'undefined';
const getConnection = () => (hasNav() ? (navigator.connection || navigator.mozConnection || navigator.webkitConnection || null) : null);

let events = [];
let last = null;
const listeners = new Set();

function prune(now = Date.now()) {
  events = events.filter((t) => now - t < OBSERVED_WINDOW_MS);
}

export function quality() {
  prune();
  return classify({
    onLine: hasNav() ? navigator.onLine !== false : true,
    connection: getConnection(),
    observed: events.length,
  });
}

function emit() {
  const q = quality();
  if (q === last) return;
  const prev = last;
  last = q;
  for (const cb of listeners) {
    try { cb(q, prev); } catch { /* a listener must not break the others */ }
  }
}

/** Call when a request timed out or audio stalled. Two within two minutes mark the link as slow. */
export function noteSlow() {
  events.push(Date.now());
  emit();
}

/** Call when a request or buffer finished promptly, so a passing dip does not stick. */
export function noteOk() {
  if (!events.length) return;
  events = [];
  emit();
}

export function onChange(cb) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export const isSlow = () => quality() === 'slow';
export const isOffline = () => quality() === 'offline';

/** Scale a timeout to the link. Slow links get three times longer; offline fails fast. */
export function timeoutFor(ms) {
  const q = quality();
  if (q === 'slow') return ms * SLOW_TIMEOUT_FACTOR;
  if (q === 'offline') return Math.min(ms, 1500);
  return ms;
}

export const COPY = {
  slow: 'Slow connection. Audio may pause to load. Your saved briefing stays available.',
  offline: "You're offline. Your saved briefing is shown. Audio needs a connection.",
  back: 'Back online.',
};

let notifier = null;

/** Show a message through the app's toast, if the app has registered one. */
export function say(message, opts) {
  if (notifier) notifier(message, opts);
}

let bannerEl = null;

function banner() {
  if (bannerEl || typeof document === 'undefined') return bannerEl;
  bannerEl = document.createElement('div');
  bannerEl.id = 'netBanner';
  bannerEl.className = 'net-banner';
  bannerEl.setAttribute('role', 'status');
  bannerEl.setAttribute('aria-live', 'polite');
  bannerEl.hidden = true;
  const dot = document.createElement('span');
  dot.className = 'net-banner-dot';
  dot.setAttribute('aria-hidden', 'true');
  const text = document.createElement('span');
  text.className = 'net-banner-text';
  bannerEl.append(dot, text);
  document.body.appendChild(bannerEl);
  return bannerEl;
}

function render(q, prev, notify) {
  const el = banner();
  if (!el) return;
  if (q === 'ok') {
    el.hidden = true;
    document.documentElement.classList.remove('net-slow', 'net-offline');
    if ((prev === 'slow' || prev === 'offline') && notify) notify(COPY.back, { type: 'success', ms: 2200 });
    return;
  }
  el.querySelector('.net-banner-text').textContent = COPY[q];
  el.dataset.state = q;
  el.hidden = false;
  document.documentElement.classList.toggle('net-slow', q === 'slow');
  document.documentElement.classList.toggle('net-offline', q === 'offline');
}

/** Wire up browser events and the banner. `notify` is the app's toast function. */
export function initNetwork(notify) {
  if (typeof window === 'undefined') return;
  notifier = notify;
  last = quality();
  render(last, null, notify);
  onChange((q, prev) => render(q, prev, notify));
  window.addEventListener('online', emit);
  window.addEventListener('offline', emit);
  getConnection()?.addEventListener?.('change', emit);
  // A stall that has long passed should not keep the banner up.
  setInterval(emit, 15000);
}
