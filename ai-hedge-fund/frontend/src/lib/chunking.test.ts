import { describe, expect, it } from "vitest";

import { VENDOR_CHUNKS, marks, vendorChunk } from "./chunking";

const nm = (pkg: string, file = "index.js") => `/repo/node_modules/${pkg}/${file}`;

describe("marks", () => {
  it("anchors a bare marker on the end of the package name", () => {
    expect(marks(nm("react"), "react")).toBe(true);
    expect(marks(nm("react-is"), "react")).toBe(false);
    expect(marks(nm("react-smooth"), "react")).toBe(false);
  });

  it("keeps prefix semantics for markers written with a trailing dash", () => {
    expect(marks(nm("d3-scale"), "d3-")).toBe(true);
    expect(marks(nm("d3-shape"), "d3-")).toBe(true);
  });

  it("matches through a nested or pnpm-shaped path", () => {
    expect(marks("/r/node_modules/.pnpm/react@19.2.4/node_modules/react/i.js", "react")).toBe(true);
    expect(marks(nm("recharts", "node_modules/react-is/index.js"), "react")).toBe(false);
  });
});

describe("vendorChunk", () => {
  it("leaves our own source unassigned", () => {
    expect(vendorChunk("/repo/src/lib/chunking.ts")).toBeUndefined();
  });

  /**
   * The react chunk must stay a dependency leaf. `react-router` pulls `cookie`
   * and `set-cookie-parser` into `vendor`, and `vendor` imports React back —
   * that cycle is what served production a blank page.
   */
  it.each([
    ["react", "react"],
    ["react-dom", "react"],
    ["scheduler", "react"],
    ["react-router", "vendor"],
    ["react-router-dom", "vendor"],
    ["react-is", "vendor"],
    ["hoist-non-react-statics", "vendor"],
  ])("puts %s in the %s chunk", (pkg, chunk) => {
    expect(vendorChunk(nm(pkg))).toBe(chunk);
  });

  /**
   * Every member of a family belongs with its family. A sibling left in
   * `vendor` imports its own scope back out of the named chunk and closes a
   * cycle. `@sentry-internal/*` did exactly that, and only on builds where
   * `VITE_SENTRY_DSN` was set and Sentry survived tree-shaking.
   */
  it.each([
    ["@sentry/react", "sentry"],
    ["@sentry/browser", "sentry"],
    ["@sentry/core", "sentry"],
    ["@sentry-internal/replay", "sentry"],
    ["@sentry-internal/replay-canvas", "sentry"],
    ["@sentry-internal/browser-utils", "sentry"],
    ["@sentry-internal/feedback", "sentry"],
    ["recharts", "charts"],
    ["recharts-scale", "charts"],
    ["lightweight-charts", "charts"],
    ["@tanstack/react-query", "query"],
    ["@tanstack/query-core", "query"],
  ])("keeps %s with its family in the %s chunk", (pkg, chunk) => {
    expect(vendorChunk(nm(pkg))).toBe(chunk);
  });

  it("sends anything unclaimed to vendor", () => {
    expect(vendorChunk(nm("cookie"))).toBe("vendor");
    expect(vendorChunk(nm("set-cookie-parser"))).toBe("vendor");
  });

  /**
   * A scoped marker with no `/` would match every package in the scope by
   * accident of the boundary rule rather than by intent. Assert the shape of
   * the table itself so a future edit cannot quietly widen a marker.
   */
  it("declares no marker that is an unanchored substring of another", () => {
    const all = Object.values(VENDOR_CHUNKS).flat();
    for (const marker of all) {
      const others = all.filter((m) => m !== marker && !m.endsWith("-"));
      for (const other of others) {
        expect(
          marker !== other && other.startsWith(`${marker}/`),
          `${marker} swallows ${other}`,
        ).toBe(false);
      }
    }
  });
});
