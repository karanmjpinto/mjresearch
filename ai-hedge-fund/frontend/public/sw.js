/* Service worker: the app shell, and deliberately nothing else.
 *
 * The one decision in this file is what NOT to cache.
 *
 * Caching API responses is the obvious thing to do for a phone and it is
 * wrong here. This app's whole argument is that stale is fine and stale-and-
 * silent is not: a screen carries the date it was built and a fingerprint of
 * the rules it was built under, precisely so a run scored last week cannot
 * present itself as current. A service worker quietly replaying yesterday's
 * `/api/screeners/cached` would reintroduce that failure one layer lower,
 * where none of those labels can see it — the page would render old rows with
 * old timestamps and no way for the reader to tell a cached response from a
 * live one.
 *
 * So: the shell is cached so the app launches instantly and survives your
 * machine being asleep, and every `/api` request goes to the network. When
 * the network is not there the request fails, and BackendGate already knows
 * how to say "your machine is unreachable" — which is the honest answer, and
 * better than silently showing data of unknown age.
 */

const SHELL = "mj-shell-v1";

/* Only what is needed to paint the frame. Hashed build assets are cached on
 * first use below rather than listed here, because their names change every
 * build and a stale list would fail the whole install. */
const SHELL_URLS = [
  "/",
  "/manifest.webmanifest",
  "/icon-192.png",
  "/fonts/DepartureMono-Regular.woff2",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      .then((c) => c.addAll(SHELL_URLS))
      /* One missing file must not block activation and leave the previous
       * worker serving an older shell for ever. */
      .catch(() => undefined)
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Never the API, and never another origin. See the header comment.
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api")) return;

  /* Navigations: network first, shell as the fallback. This is a single-page
   * app, so any path has to resolve to the same document — falling back to a
   * cached "/" is what makes a bookmarked /research/ABC open offline rather
   * than 404. */
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() =>
        caches.match("/").then((hit) => hit ?? Response.error()),
      ),
    );
    return;
  }

  /* Static assets: cache first, then network, storing what comes back. Build
   * output is content-hashed, so a cached hit is never the wrong version. */
  event.respondWith(
    caches.match(req).then(
      (hit) =>
        hit ??
        fetch(req).then((res) => {
          if (res.ok && res.type === "basic") {
            const copy = res.clone();
            caches.open(SHELL).then((c) => c.put(req, copy));
          }
          return res;
        }),
    ),
  );
});
