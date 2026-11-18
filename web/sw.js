const CACHE = "paperfeed";
const SHELL = [
  "./",
  "index.html",
  "style.css",
  "app.js",
  "store.js",
  "bibtex.js",
  "manifest.webmanifest",
  "icons/icon.svg",
  "icons/icon-192.png",
  "fonts/stix-two-text-latin-wght-normal.woff2",
  "fonts/stix-two-text-latin-wght-italic.woff2",
  "fonts/stix-two-text-latin-ext-wght-normal.woff2",
  "fonts/stix-two-text-latin-ext-wght-italic.woff2",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  // The feed comes from GitHub and is cached by the app itself.
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  // Fonts and icons never change, so the cached copy is enough.
  if (/\/(fonts|icons)\//.test(url.pathname)) {
    event.respondWith(caches.match(request).then((cached) => cached ?? fetch(request)));
    return;
  }

  // Everything else opens from the cache and is refreshed in the background,
  // so a new version shows up on the next launch.
  const network = fetch(request);
  event.waitUntil(
    network
      .then(async (response) => {
        if (response.ok) {
          const cache = await caches.open(CACHE);
          await cache.put(request, response.clone());
        }
      })
      .catch(() => {}),
  );
  event.respondWith(
    caches.match(request).then((cached) => cached ?? network.then((response) => response.clone())),
  );
});
