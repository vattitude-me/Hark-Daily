// Connection awareness for weak mobile networks (low 4G, 3G, patchy coverage).
//
// Wi-Fi needs none of this. On a weak link we do three things: stretch request timeouts so a slow
// download is not abandoned half way, hold back background preloading so it does not starve the clip
// that is playing, and tell the listener what is going on instead of failing silently.
//
// Two kinds of signal, used differently:
// - Evidence: the browser is offline, or audio stalled or a request timed out. Only evidence shows
//   anything to the listener.
// - Hints: navigator.connection. Chrome's downlink and rtt are rough estimates that drift on fast
//   Wi-Fi (1.5 Mbps is a common reading there), so hints only tune timeouts and preloading, silently.
//
// This module imports nothing from the app so it can be tested on its own.

const SLOW_TYPES = new Set(['slow-2g', '2g', '3g']);
const SLOW_DOWNLINK_MBPS = 1.5;
const SLOW_RTT_MS = 450;
const OBSERVED_WINDOW_MS = 2 * 60 * 1000;
const OBSERVED_THRESHOLD = 2;
const SLOW_TIMEOUT_FACTOR = 3;

/**
 * What the listener is told. Pure. `observed` counts request timeouts and failed loads in the last two
 * minutes; one can be bad luck, two is a pattern. `stalled` means playback sat waiting for data for
 * several seconds in that window, which is proof on its own.
 */
export function classify({ onLine = true, observed = 0, stalled = false } = {}) {
  if (onLine === false) return 'offline';
  if (stalled || observed >= OBSERVED_THRESHOLD) return 'slow';
  return 'ok';
}

/** True when navigator.connection suggests a weak link. Pure. Never shown to the listener. */
export function weakHint(connection) {
  if (!connection) return false;
  if (connection.saveData) return true;
  if (SLOW_TYPES.has(connection.effectiveType)) return true;
  if (typeof connection.downlink === 'number' && connection.downlink > 0 && connection.downlink < SLOW_DOWNLINK_MBPS) return true;
  if (typeof connection.rtt === 'number' && connection.rtt > SLOW_RTT_MS) return true;
  return false;
}

const hasNav = () => typeof navigator !== 'undefined';
const getConnection = () => (hasNav() ? (navigator.connection || navigator.mozConnection || navigator.webkitConnection || null) : null);

let events = [];
let stalledAt = -Infinity;
let last = null;
const listeners = new Set();

function prune(now = Date.now()) {
  events = events.filter((t) => now - t < OBSERVED_WINDOW_MS);
}

export function quality() {
  prune();
  return classify({
    onLine: hasNav() ? navigator.onLine !== false : true,
    observed: events.length,
    stalled: Date.now() - stalledAt < OBSERVED_WINDOW_MS,
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

/** Call when a request timed out or a clip failed to load. Two within two minutes mark the link slow. */
export function noteSlow() {
  events.push(Date.now());
  emit();
}

/** Call when playback has waited several seconds for data. Marks the link slow for two minutes. */
export function noteStall() {
  stalledAt = Date.now();
  emit();
}

/** Call when a large download finished promptly, so an earlier timeout does not stick. */
export function noteOk() {
  if (!events.length && stalledAt === -Infinity) return;
  events = [];
  stalledAt = -Infinity;
  emit();
}

export function onChange(cb) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export const isOffline = () => quality() === 'offline';
/** For tuning, not for messages: slow by evidence, or the browser hints at a weak link. */
export const isSlow = () => {
  const q = quality();
  return q === 'slow' || (q === 'ok' && weakHint(getConnection()));
};

/** Scale a timeout to the link. Slow links get three times longer; offline fails fast. */
export function timeoutFor(ms) {
  if (isOffline()) return Math.min(ms, 1500);
  return isSlow() ? ms * SLOW_TIMEOUT_FACTOR : ms;
}

// Short enough for one line in the header on a 360px phone.
export const COPY = {
  slow: 'Slow connection',
  offline: "You're offline",
  back: 'Back online',
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
  bannerEl.title = 'Tap to dismiss';
  bannerEl.addEventListener('click', () => showBanner(false));
  document.body.appendChild(bannerEl);
  return bannerEl;
}

/**
 * Put the banner where it cannot cover anything. In the player view it takes the logo's place in the
 * top bar, between the menu and story-list buttons. Anywhere else it floats at the top of the page.
 */
function placeBanner(el) {
  const bar = document.getElementById('cleanTopbar');
  const inBar = Boolean(bar && bar.offsetParent !== null);
  if (inBar && el.parentNode !== bar) {
    const brand = bar.querySelector('.clean-brand');
    if (brand) brand.after(el); else bar.append(el);
  } else if (!inBar && el.parentNode !== document.body) {
    bar?.classList.remove('net-banner-on');
    document.body.appendChild(el);
  }
  el.classList.toggle('net-banner-inline', inBar);
}

function showBanner(on) {
  const el = banner();
  if (!el) return;
  if (on) placeBanner(el);
  el.hidden = !on;
  el.parentNode?.classList?.toggle('net-banner-on', on && el.parentNode !== document.body);
}

const SLOW_BANNER_MS = 8000;
const SLOW_BANNER_COOLDOWN_MS = 2 * 60 * 1000;
let slowShownAt = -Infinity;
let hideTimer = null;

/**
 * Pure decision for a quality change. The slow banner is a heads-up, not a fixture: it hides itself
 * after a few seconds and does not come back for two minutes. Offline stays until the link returns.
 * "Back online" is only said after being offline, never after a slow patch.
 */
export function bannerAction(q, prev, { now = Date.now(), lastSlowAt = -Infinity } = {}) {
  if (q === 'offline') return { show: true, autoHideMs: 0, back: false };
  const back = prev === 'offline';
  if (q === 'ok' || now - lastSlowAt < SLOW_BANNER_COOLDOWN_MS) return { show: false, back };
  return { show: true, autoHideMs: SLOW_BANNER_MS, back };
}

function render(q, prev, notify) {
  const el = banner();
  if (!el) return;
  document.documentElement.classList.toggle('net-slow', q === 'slow');
  document.documentElement.classList.toggle('net-offline', q === 'offline');
  const act = bannerAction(q, prev, { lastSlowAt: slowShownAt });
  clearTimeout(hideTimer);
  if (act.back && notify) notify(COPY.back, { type: 'success', ms: 2200 });
  if (!act.show) {
    showBanner(false);
    return;
  }
  el.querySelector('.net-banner-text').textContent = COPY[q];
  el.dataset.state = q;
  showBanner(true);
  if (q === 'slow') slowShownAt = Date.now();
  if (act.autoHideMs) hideTimer = setTimeout(() => showBanner(false), act.autoHideMs);
}

/** Wire up browser events and the banner. `notify` is the app's toast function. */
export function initNetwork(notify) {
  if (typeof window === 'undefined') return;
  notifier = notify;
  last = quality();
  render(last, null, notify);
  onChange((q, prev) => render(q, prev, notify));
  // Stalls from before the drop say nothing about the link we came back on.
  window.addEventListener('online', () => { events = []; stalledAt = -Infinity; emit(); });
  window.addEventListener('offline', emit);
  // A stall that has long passed should not keep the banner up.
  setInterval(emit, 15000);
}
