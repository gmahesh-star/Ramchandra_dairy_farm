const CACHE_NAME = 'dairy-pwa-v4';
const ASSETS = [
    '/login',
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/images/icon-192.png',
    '/static/images/icon-512.png',
    '/static/images/mascot.png'
];

self.addEventListener('install', (event) => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(ASSETS);
        })
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter(key => key !== CACHE_NAME)
                    .map(key => caches.delete(key))
            );
        })
    );
});

self.addEventListener('fetch', (event) => {
    // Only handle GET requests and avoid internal Render/Analytics calls
    if (event.request.method !== 'GET') return;

    event.respondWith(
        fetch(event.request).catch(() => {
            return caches.match(event.request);
        })
    );
});
