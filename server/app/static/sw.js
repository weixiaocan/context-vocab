const CACHE_NAME = "vocab-pwa-v2";
const REVIEW_PAGE = "/review";

self.addEventListener("install", event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.add(REVIEW_PAGE).catch(() => {}))
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches
      .keys()
      .then(keys =>
        Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then(response => {
          // Don't let the login page (redirected) or an error replace the cached review page.
          if (response.ok && !response.redirected) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(REVIEW_PAGE, copy));
          }
          return response;
        })
        .catch(() => caches.match(REVIEW_PAGE).then(cached => cached || caches.match(request)))
    );
    return;
  }

  if (
    url.pathname.startsWith("/audio/") ||
    url.pathname.startsWith("/icon") ||
    url.pathname === "/manifest.webmanifest"
  ) {
    event.respondWith(
      caches.match(request).then(
        cached =>
          cached ||
          fetch(request).then(response => {
            // Only cache successful responses: a 401 (expired login) or 404
            // (no audio yet) must not stick and silence the word forever.
            if (response.ok && response.status === 200) {
              const copy = response.clone();
              caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
            }
            return response;
          })
      )
    );
  }
});
