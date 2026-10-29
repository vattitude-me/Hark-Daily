// Offline shell: stale-while-revalidate for static shell assets, network-first for HTML.
// Supabase (data, audio) and CDN requests are cross-origin and go straight to the network.
const CACHE = 'hark-daily-v28';
const SHELL = [
  '/', '/config.js', '/css/styles.css', '/manifest.webmanifest', '/audio/gap.mp3',
  '/fonts/plus-jakarta-sans.woff2', '/fonts/space-grotesk.woff2',
  '/icons/icon.svg', '/icons/icon-96.png', '/icons/icon-192.png', '/icons/icon-512.png',
  '/js/vendor/supabase.min.js',
  '/js/app.js', '/js/api.js', '/js/storypack.js', '/js/player.js', '/js/sheets.js', '/js/landing.js',
  '/js/design.js', '/js/audio-processor.js', '/js/pages/sources.js', '/js/pages/settings.js', '/js/pages/admin.js',
  '/sitemap.xml', '/robots.txt'
];

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
  // Audio streams with range requests; let the browser handle it directly.
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.endsWith('.mp3')) return;

  // Stale-while-revalidate for static assets (instant load from local device cache)
  const isStatic = url.pathname.startsWith('/fonts/') ||
                   url.pathname.startsWith('/js/') ||
                   url.pathname.startsWith('/css/') ||
                   url.pathname.startsWith('/icons/') ||
                   url.pathname === '/manifest.webmanifest';

  if (isStatic) {
    e.respondWith(
      caches.match(e.request).then((cached) => {
        const fetchPromise = fetch(e.request).then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(e.request, copy));
          }
          return res;
        }).catch(() => null);
        return cached || fetchPromise;
      })
    );
    return;
  }

  // Network-first for HTML shell so latest deploy is picked up immediately
  e.respondWith(
    fetch(e.request).then((res) => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
      }
      return res;
    }).catch(() => caches.match(e.request).then((r) => r || caches.match('/')))
  );
});

self.addEventListener('push', (e) => {
  let data = {};
  try {
    data = e.data ? e.data.json() : {};
  } catch {
    try { data = { body: e.data.text() }; } catch { /* ignore */ }
  }
  e.waitUntil(self.registration.showNotification(data.title || 'Hark Daily', {
    body: data.body || "Today's briefing is ready.",
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-96.png',
    tag: 'hark-daily',
    renotify: true,
    vibrate: [200, 100, 200],
    data: { url: data.url || '/' },
  }));
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const target = e.notification.data?.url || '/';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
    for (const w of wins) {
      if ('focus' in w) {
        if ('navigate' in w && target && target !== '/') w.navigate(target);
        return w.focus();
      }
    }
    return self.clients.openWindow(target);
  }));
});

