// Offline shell: static assets cache-first, API network-first, audio straight from the network.
const CACHE = 'morning-brief-v1';
const SHELL = ['/', '/css/styles.css', '/js/app.js', '/js/api.js', '/js/player.js', '/js/sheets.js',
  '/icons/icon.svg', '/manifest.webmanifest'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/media/')) return;
  if (url.pathname.startsWith('/api/')) {
    if (url.pathname.startsWith('/api/voices/preview')) return;
    e.respondWith(fetch(e.request).then((res) => {
      if (res.ok && url.pathname.startsWith('/api/briefing')) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
      }
      return res;
    }).catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(fetch(e.request).then((res) => {
    if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
    return res;
  }).catch(() => caches.match(e.request).then((r) => r || caches.match('/'))));
});
