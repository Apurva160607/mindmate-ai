
const CACHE_NAME = "mindmate-static-v1";

self.addEventListener("install", (event) => {
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        (async () => {
            const keys = await caches.keys();

            await Promise.all(
                keys
                    .filter((key) => key.startsWith("mindmate-static-") && key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            );

            await self.clients.claim();
        })()
    );
});

self.addEventListener("fetch", (event) => {
    const url = new URL(event.request.url);

    if (
        event.request.method !== "GET" ||
        url.origin !== self.location.origin ||
        !url.pathname.startsWith("/app/static/")
    ) {
        return;
    }

    event.respondWith(
        (async () => {
            const cache = await caches.open(CACHE_NAME);
            const cached = await cache.match(event.request);

            if (cached) return cached;

            try {
                const response = await fetch(event.request);

                if (response.ok) {
                    await cache.put(event.request, response.clone());
                }

                return response;
            } catch {
                return new Response("Offline: resource unavailable", {
                    status: 503
                });
            }
        })()
    );
});
