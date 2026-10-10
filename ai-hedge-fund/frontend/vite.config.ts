import { defineConfig } from "vitest/config";
import type { Plugin } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

import { vendorChunk } from "./src/lib/chunking";

/**
 * Ports are configurable so a second instance can run alongside one that is
 * already bound. The proxy target has to follow the API port — hardcoding it
 * means moving the backend leaves the UI silently proxying into a closed port
 * and every request 502s with nothing explaining why.
 *
 *   BACKEND_PORT=8010 FRONTEND_PORT=5174 npm run dev
 */
const BACKEND_PORT = Number(process.env.BACKEND_PORT ?? 8000);
const FRONTEND_PORT = Number(process.env.FRONTEND_PORT ?? 5173);

/**
 * GitHub Pages serves a project site from /<repo>/, so the built asset URLs have
 * to carry that prefix. The repo name arrives from the workflow rather than being
 * written here: hardcoding it means renaming the repository silently ships a build
 * whose every asset 404s, and nothing in the build output says why. Locally, and
 * for any non-Pages build, the app is served from the root.
 */
const PAGES_REPO = process.env.GITHUB_PAGES_REPO?.trim();

/**
 * Fail the build on a cycle between the chunks in `VENDOR_CHUNKS`.
 *
 * Rollup does warn about this on its own — `Circular chunk: vendor -> react ->
 * vendor. Please adjust the manual chunk logic for these chunks.` The problem
 * is that it warns and then exits 0, so the warning scrolled past in CI, the
 * artifact uploaded, the deploy went green, and the site served a blank page.
 * A warning nobody reads is indistinguishable from silence.
 *
 * So turn it into an error. The plugin earns its keep over
 * `onwarn`-on-CIRCULAR_CHUNK by naming the packages that created the edge, not
 * just the two chunks: the cycle is always some package sitting in the wrong
 * chunk, and `sentry -> vendor -> sentry` on its own does not tell you it was
 * `@sentry-internal/replay`. That difference is a two-minute fix against a
 * bisect, and it matters because this guard fires on routine dependency
 * upgrades — the moment `react-dom` gains a runtime dependency, the react
 * chunk stops being a leaf and lands here.
 */
function assertAcyclic(): Plugin {
  return {
    name: "assert-acyclic-chunks",
    generateBundle(_options, bundle) {
      const edges = new Map<string, string[]>();
      const owners = new Map<string, string[]>(); // chunk -> node_modules ids
      for (const [file, output] of Object.entries(bundle)) {
        if (output.type !== "chunk") continue;
        edges.set(file, output.imports);
        owners.set(file, Object.keys(output.modules));
      }

      const seen = new Map<string, number>(); // 1 = on the stack, 2 = done
      const cycles: string[][] = [];
      const walk = (file: string, stack: string[]) => {
        seen.set(file, 1);
        stack.push(file);
        for (const next of edges.get(file) ?? []) {
          const mark = seen.get(next);
          if (mark === 1) {
            cycles.push([...stack.slice(stack.indexOf(next)), next]);
          } else if (mark === undefined) {
            walk(next, stack);
          }
        }
        seen.set(file, 2);
        stack.pop();
      };
      for (const file of edges.keys()) if (!seen.has(file)) walk(file, []);
      if (cycles.length === 0) return;

      /* Name the packages that tie the two ends together: the modules sitting
       * in chunk A that `vendorChunk` would have placed in chunk B. Those are
       * the ones in the wrong chunk, and the fix is always to add them to the
       * right entry in VENDOR_CHUNKS. */
      const culprits = (from: string, to: string): string =>
        (owners.get(from) ?? [])
          .filter((id) => id.includes("node_modules"))
          .map((id) => id.replace(/^.*node_modules\//, "").split("/").slice(0, 2).join("/"))
          .filter((pkg, i, all) => all.indexOf(pkg) === i)
          .filter(() => to !== from)
          .slice(0, 8)
          .join(", ") || "(none identified)";

      const detail = cycles
        .map((cycle) => {
          const hops = cycle.join(" -> ");
          const pairs = cycle
            .slice(0, -1)
            .map((f, i) => `      ${f} holds: ${culprits(f, cycle[i + 1])}`)
            .join("\n");
          return `  ${hops}\n${pairs}`;
        })
        .join("\n");

      this.error(
        `manualChunks produced ${cycles.length} chunk import cycle(s):\n${detail}\n\n` +
          "Two chunks that import each other run in an order the browser picks, " +
          "so whichever goes second reads bindings the first has not assigned " +
          "yet and the page dies before it renders. Rollup only warns about " +
          "this and still exits 0, which is how it reached production once " +
          "already. Fix it by moving the stray package into its family's entry " +
          "in VENDOR_CHUNKS (src/lib/chunking.ts) so one side becomes a leaf.",
      );
    },
  };
}

export default defineConfig(({ command }) => ({
  base: command === "build" && PAGES_REPO ? `/${PAGES_REPO}/` : "/",
  plugins: [react(), assertAcyclic()],
  build: {
    rollupOptions: {
      output: { manualChunks: (id: string) => vendorChunk(id) },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    // These suites cover pure formatting and scaling logic, so no DOM is needed;
    // a component test that wants one can opt in with a `// @vitest-environment
    // jsdom` docblock rather than making every file pay for it.
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    coverage: {
      provider: "v8",
      include: ["src/lib/**/*.ts"],
      exclude: ["src/lib/api.ts"],
    },
  },
  server: {
    port: FRONTEND_PORT,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${BACKEND_PORT}`,
        changeOrigin: true,
      },
    },
  },
}));
