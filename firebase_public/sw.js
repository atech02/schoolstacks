/**
 * static/sw.js — EduManage Service Worker
 * Security-first caching strategy:
 * - Caches only versioned static assets (/static/*, /manifest.json) and the /offline fallback page.
 * - NEVER caches authenticated HTML pages, private school records, Lipila payment endpoints, or POST requests.
 * - Immediately activates new versions and purges outdated caches.
 */
const CACHE_VERSION = "edumanage-static-v2";
const PRECACHE_URLS = [
  "/offline",
  "/manifest.json",
  "/static/css/brand-theme.css",
  "/static/js/shader-gradient-hero.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];

const NEVER_CACHE_PREFIXES = [
  "/admin",
  "/teacher",
  "/student",
  "/parent",
  "/superadmin",
  "/billing",
  "/login",
  "/logout",
  "/change-password",
  "/portal",
  "/register",
  "/verify",
  "/health"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_VERSION)
          .map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Never intercept non-GET requests (e.g. POST forms, webhooks, payments)
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== self.location.origin) {
    return;
  }

  // Never cache private/authenticated/payment routes; go network-only with offline fallback for navigation
  const isPrivateRoute = NEVER_CACHE_PREFIXES.some((prefix) =>
    url.pathname.startsWith(prefix)
  );

  if (request.mode === "navigate" || isPrivateRoute) {
    event.respondWith(
      fetch(request).catch(() => caches.match("/offline"))
    );
    return;
  }

  // Static assets (/static/*, /manifest.json): Stale-While-Revalidate
  if (url.pathname.startsWith("/static/") || url.pathname === "/manifest.json") {
    event.respondWith(
      caches.open(CACHE_VERSION).then((cache) =>
        cache.match(request).then((cachedResponse) => {
          const fetchPromise = fetch(request)
            .then((networkResponse) => {
              if (networkResponse && networkResponse.status === 200) {
                cache.put(request, networkResponse.clone());
              }
              return networkResponse;
            })
            .catch(() => cachedResponse);
          return cachedResponse || fetchPromise;
        })
      )
    );
  }
});
