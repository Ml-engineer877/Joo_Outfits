const CACHE_NAME = 'teestore-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/add-product-view',
  '/restock-view'
];

// Install Service Worker and cache the core application layout pages
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
});

// Network-first falling back to cache strategy to guarantee fresh financial data
self.addEventListener('fetch', (event) => {
  event.respondWith(
    fetch(event.request)
      .catch(() => {
        return caches.match(event.request);
      })
  );
});