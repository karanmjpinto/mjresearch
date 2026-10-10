/**
 * Which vendor chunk each node_modules package belongs to.
 *
 * This lives in `src/lib` rather than in `vite.config.ts` for one reason: the
 * config file is invisible to both checkers. `tsconfig.json` scopes `include`
 * to `src`, so `tsc` never type-checks it, and Vite transpiles it with esbuild,
 * which strips types without reading them. Nothing could test the rule that
 * decides the chunk layout. Here, `chunking.test.ts` covers it — and the first
 * table test written against this file caught a live `@sentry-internal` bug
 * that review had missed.
 */

/**
 * Libraries that change on their own release schedule, not ours, get their own
 * chunks. Without this they land in whichever route chunk happened to import
 * them first, so every deploy of our own code invalidates React and the chart
 * libraries too, and a returning visitor re-downloads ~300 kB that did not
 * change. Splitting them means an app deploy busts only the app chunks.
 *
 * `charts` is the pair that made the single bundle 1.36 MB. It stays one chunk
 * rather than two because no screen loads only one of them.
 *
 * **A split chunk must not import a chunk that imports it back.** ES modules
 * permit the cycle and the browser resolves it by running one of the two
 * first — against bindings the other has not assigned yet. Anything either
 * chunk does at load time, which for a bundled CommonJS dependency is the
 * whole module factory, then reads `undefined`. That is not a warning or a
 * degraded render: the entry throws before React mounts and the page is
 * blank, served with a 200 by a backend answering every route correctly.
 * It is the exact failure this configuration shipped — see `assertAcyclic`.
 *
 * `react` is therefore `react` + `react-dom` + `scheduler` and nothing else:
 * that set depends on nothing outside itself, so the chunk is a leaf and
 * every other chunk can import it freely. `react-router` is deliberately NOT
 * in it — it depends on `cookie` and `set-cookie-parser`, which land in
 * `vendor`, which would point the react chunk back at vendor and close the
 * loop. It rides in `vendor` instead, and ships on vendor's cadence.
 *
 * **List every member of a family, including the siblings under a different
 * name.** A package left off this list falls to `vendor` while the rest of its
 * family sits in a named chunk, and the two then import each other. That is
 * how `@sentry-internal/*` broke: `@sentry/browser` imports it and it imports
 * `@sentry/core` back, so the first build with `VITE_SENTRY_DSN` set — the
 * first build where Sentry is not tree-shaken away — failed on
 * `sentry -> vendor -> sentry`. The same trap is loaded for
 * `@tanstack/react-query-devtools` and `recharts-scale`.
 */
export const VENDOR_CHUNKS: Record<string, string[]> = {
  react: ["react", "react-dom", "scheduler"],
  charts: ["recharts", "recharts-scale", "lightweight-charts", "d3-", "victory-"],
  query: ["@tanstack/react-query", "@tanstack/query-"],
  sentry: ["@sentry", "@sentry-internal"],
};

/**
 * A marker names a package, not a prefix of one. `react` matching `react-is` is
 * what took production down: `react-is` was swept into the `react` chunk while
 * its only caller, `hoist-non-react-statics`, stayed in `vendor`. `vendor` then
 * ran the CommonJS factory at load time against an exports object declared in a
 * chunk that had not executed yet, and the page died on "Cannot set properties
 * of undefined (setting 'AsyncMode')" before React ever mounted — a blank
 * screen, served with a 200, by a backend answering every route correctly.
 *
 * So anchor each marker on the separator that ends a package name. Markers
 * written with a trailing `-` are deliberate family prefixes — `d3-scale`,
 * `d3-shape` and the rest arrive as a dozen separate packages — and keep
 * prefix semantics.
 */
export function marks(id: string, marker: string): boolean {
  const at = `node_modules/${marker}`;
  return marker.endsWith("-") ? id.includes(at) : id.includes(`${at}/`);
}

export function vendorChunk(id: string): string | undefined {
  if (!id.includes("node_modules")) return undefined;
  for (const [chunk, markers] of Object.entries(VENDOR_CHUNKS)) {
    if (markers.some((m) => marks(id, m))) return chunk;
  }
  return "vendor";
}
