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

export default defineConfig(({ command }) => ({
  base: command === "build" && PAGES_REPO ? `/${PAGES_REPO}/` : "/",
  plugins: [react()],
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
