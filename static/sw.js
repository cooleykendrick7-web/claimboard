// ClaimBoard service worker: cache ONLY the app shell (icons/manifest), never data.
// Claim data always comes fresh from the API so numbers are real-time.
const CACHE = 'claimboard-shell-v1';
const SHELL = ['/static/icons/icon-192.png', '/static/icons/icon-512.png', '/static/icons/apple-touch-icon.png', '/manifest.webmanifest'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => { e.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (SHELL.includes(url.pathname)) { e.respondWith(caches.match(e.request).then(r => r || fetch(e.request))); }
  // everything else: network only (live data)
});
