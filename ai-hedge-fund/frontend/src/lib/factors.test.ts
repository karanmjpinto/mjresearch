import { describe, expect, it } from "vitest";
import type { FactorRow, FactorStats } from "@/lib/api";
import {
  cumulative,
  legOf,
  monthLabel,
  previousMonth,
  replication,
  signedPct,
  yearsBefore,
} from "./factors";

const months = ["2020-11", "2020-12", "2021-01", "2021-02", "2021-03"];

describe("cumulative", () => {
  it("compounds from a starting dollar dated the month before", () => {
    const pts = cumulative({ start: 1, returns: [0.1, -0.1, 0.05] }, months);
    expect(pts.map((p) => p.month)).toEqual([
      "2020-11",
      "2020-12",
      "2021-01",
      "2021-02",
    ]);
    expect(pts[0]!.value).toBe(1);
    expect(pts[3]!.value).toBeCloseTo(1.1 * 0.9 * 1.05);
  });

  it("carries a missing month flat instead of reading it as zero", () => {
    const pts = cumulative({ start: 0, returns: [0.1, null, 0.1] }, months);
    expect(pts[2]!.value).toBeCloseTo(1.1);
    expect(pts[2]!.ret).toBeNull();
    expect(pts[3]!.value).toBeCloseTo(1.21);
  });

  it("starts the window at `from`", () => {
    const pts = cumulative(
      { start: 0, returns: [0.5, 0.5, 0.1, 0.1] },
      months,
      "2021-01",
    );
    expect(pts[0]).toEqual({ month: "2020-12", value: 1, ret: null });
    expect(pts.at(-1)!.value).toBeCloseTo(1.21);
  });
});

describe("month arithmetic", () => {
  it("steps back across a year", () => {
    expect(previousMonth("2021-01")).toBe("2020-12");
    expect(previousMonth("2021-07")).toBe("2021-06");
  });
  it("goes back whole years", () => {
    expect(yearsBefore("2024-12", 10)).toBe("2014-12");
  });
  it("labels a month", () => {
    expect(monthLabel("2024-12")).toBe("Dec 2024");
  });
});

describe("legOf", () => {
  it("keeps a wide middle band", () => {
    expect(legOf(75)).toBe("long");
    expect(legOf(55)).toBe("middle");
    expect(legOf(45)).toBe("middle");
    expect(legOf(12)).toBe("short");
  });
});

const s = (sharpe: number, ann_return = sharpe / 10): FactorStats => ({
  months: 120,
  ann_return,
  ann_vol: 0.1,
  sharpe,
  t_stat: sharpe * 3,
});

const row = (
  id: string,
  ins: FactorStats | null,
  post: FactorStats | null,
): FactorRow => ({
  id,
  name: id,
  cite: null,
  in_sample_years: [1970, 1990],
  original_t: null,
  direction: 1,
  full: null,
  in_sample: ins,
  post_sample: post,
});

describe("replication", () => {
  it("counts a factor as held when its post-sample mean stayed positive", () => {
    const r = replication([
      row("a", s(0.8), s(0.4)),
      row("b", s(0.6), s(-0.2)),
      row("c", s(0.4), s(0.1)),
      row("d", null, s(0.3)), // untested: no in-sample half
    ]);
    expect(r.tested).toBe(3);
    expect(r.held).toBe(2);
    expect(r.medianIn).toBeCloseTo(0.6);
    expect(r.medianPost).toBeCloseTo(0.1);
  });
});

describe("signedPct", () => {
  it("uses a real minus sign and never prints −0.0%", () => {
    expect(signedPct(0.029)).toBe("+2.9%");
    expect(signedPct(-0.014)).toBe("−1.4%");
    expect(signedPct(-0.0001)).toBe("0.0%");
    expect(signedPct(null)).toBe("—");
  });
});
