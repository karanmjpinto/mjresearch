import { defineConfig } from "vite";
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

export default defineConfig(({ command }) => ({
  // On GitHub Pages the app lives at /ai-hedge-fund/; locally it's /
  base: command === "build" && process.env.GITHUB_PAGES ? "/ai-hedge-fund/" : "/",
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
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
