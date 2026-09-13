import { describe, expect, it } from "vitest";
import { compsExtent, compsPct } from "./comps-scale";

describe("compsExtent", () => {
  it("pads the extent so the outermost marks are not flush to the edge", () => {
    const e = compsExtent([100, 200]);
    expect(e.min).toBeLessThan(100);
    expect(e.min + e.span).toBeGreaterThan(200);
  });

  it("keeps a price far outside every band inside the drawing", () => {
    // Apple's real shape: bands top out at 226, the price is 332.
    const e = compsExtent([153.91, 225.76, 175.49, 199.06, 332.27]);
    const p = compsPct(332.27, e);
    expect(p).toBeGreaterThan(0);
    expect(p).toBeLessThan(100);
  });

  it("survives a set with no width rather than dividing by zero", () => {
    const e = compsExtent([50, 50, 50]);
    expect(e.span).toBeGreaterThan(0);
    expect(Number.isFinite(compsPct(50, e))).toBe(true);
  });

  it("survives a single point", () => {
    const e = compsExtent([42]);
    expect(e.span).toBeGreaterThan(0);
    expect(Number.isFinite(compsPct(42, e))).toBe(true);
  });

  it("ignores values that cannot be placed", () => {
    const clean = compsExtent([100, 200]);
    const noisy = compsExtent([100, 200, 0, -5, NaN, Infinity]);
    expect(noisy).toEqual(clean);
  });

  it("falls back to a usable scale when there is nothing to place", () => {
    const e = compsExtent([]);
    expect(e.span).toBe(1);
    expect(compsPct(0, e)).toBe(0);
  });
});

describe("compsPct", () => {
  it("puts the extremes near the ends and the middle in the middle", () => {
    const e = compsExtent([0.0001, 100]);
    expect(compsPct(50, e)).toBeGreaterThan(40);
    expect(compsPct(50, e)).toBeLessThan(60);
  });

  it("returns a placeable number for a degenerate span", () => {
    expect(compsPct(10, { min: 0, span: 0 })).toBe(0);
    expect(compsPct(NaN, { min: 0, span: 10 })).toBe(0);
  });
});
