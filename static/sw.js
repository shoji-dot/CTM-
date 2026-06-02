const CACHE_NAME = 'salescore-v1';
const STATIC_ASSETS = [
  '/static/css/style.css',
  '/static/js/main.js',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/apple-touch-icon.png',
];

// インストール：静的アセットをキャッシュ
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// アクティベート：古いキャッシュを削除
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// フェッチ：Network First（静的アセットのみCache Fallback）
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // 静的アセットはCache First
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        return cached || fetch(event.request).then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        });
      })
    );
    return;
  }

  // APIやページはNetwork First（オフライン時はフォールバックなし）
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
