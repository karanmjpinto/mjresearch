import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

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
 * Libraries that change on their own release schedule, not ours, get their own
 * chunks. Without this they land in whichever route chunk happened to import
 * them first, so every deploy of our own code invalidates React and the chart
 * libraries too, and a returning visitor re-downloads ~300 kB that did not
 * change. Splitting them means an app deploy busts only the app chunks.
 *
 * `charts` is the pair that made the single bundle 1.36 MB. It stays one chunk
 * rather than two because no screen loads only one of them.
 */
const VENDOR_CHUNKS: Record<string, string[]> = {
  react: ["react", "react-dom", "react-router", "react-router-dom"],
  charts: ["recharts", "lightweight-charts", "d3-", "victory-"],
  query: ["@tanstack/react-query"],
  sentry: ["@sentry"],
};

function vendorChunk(id: string): string | undefined {
  if (!id.includes("node_modules")) return undefined;
  for (const [chunk, markers] of Object.entries(VENDOR_CHUNKS)) {
    if (markers.some((m) => id.includes(`node_modules/${m}`))) return chunk;
  }
  return "vendor";
}

export default defineConfig(({ command }) => ({
  base: command === "build" && PAGES_REPO ? `/${PAGES_REPO}/` : "/",
  plugins: [react()],
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
