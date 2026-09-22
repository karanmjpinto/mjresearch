/**
 * Pure arithmetic behind the Factors tab, kept out of the components so it can
 * be tested without rendering anything.
 *
 * The statistics that carry a claim (Sharpe, t, annualised return) are computed
 * in Python and arrive with the payload. What lives here is drawing arithmetic:
 * compounding a window of monthly returns into a line, and reading a tilt score
 * back into words.
 */

import type { FactorRow, FactorTheme } from "@/lib/api";

export type Point = { month: string; value: number; ret: number | null };

/**
 * Growth of $1 in a long-short portfolio over the months from `from` on.
 *
 * A missing month carries the previous value forward and keeps `ret: null`,
 * so a gap draws as flat rather than as a zero return someone could hover and
 * believe. The first point is the starting dollar, dated the month before the
 * first return, so the line starts at exactly 1.
 */
export function cumulative(
  theme: Pick<FactorTheme, "start" | "returns">,
  months: string[],
  from?: string,
): Point[] {
  const out: Point[] = [];
  let v = 1;
  theme.returns.forEach((r, i) => {
    const m = months[theme.start + i];
    if (m === undefined || (from && m < from)) return;
    if (out.length === 0) {
      out.push({ month: previousMonth(m), value: 1, ret: null });
    }
    if (r != null && Number.isFinite(r)) v *= 1 + r;
    out.push({ month: m, value: v, ret: r });
  });
  return out;
}

export function previousMonth(m: string): string {
  const y = Number(m.slice(0, 4));
  const mo = Number(m.slice(5, 7));
  return mo === 1
    ? `${y - 1}-12`
    : `${y}-${String(mo - 1).padStart(2, "0")}`;
}

/** 'YYYY-MM' ten years before the given month, for the "last 10y" window. */
export function yearsBefore(m: string, years: number): string {
  return `${Number(m.slice(0, 4)) - years}${m.slice(4)}`;
}

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function monthLabel(m: string): string {
  return `${MONTHS[Number(m.slice(5, 7)) - 1] ?? "?"} ${m.slice(0, 4)}`;
}

export type Leg = "long" | "short" | "middle";

/**
 * Which side of the factor a score puts the company on.
 *
 * The middle band is deliberately wide. A percentile of 55 over a few hundred
 * names is inside the noise of which quarter the fundamentals were fetched in;
 * calling it "long" would be reading a tilt into a coin toss.
 */
export function legOf(score: number): Leg {
  if (score >= 60) return "long";
  if (score <= 40) return "short";
  return "middle";
}

export const LEG_WORD: Record<Leg, string> = {
  long: "long side",
  short: "short side",
  middle: "middle",
};

export type Replication = {
  /** Factors with both halves measured. */
  tested: number;
  /** ...of which the post-sample mean return stayed positive. */
  held: number;
  medianIn: number | null;
  medianPost: number | null;
};

function median(xs: number[]): number | null {
  if (xs.length === 0) return null;
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid]! : (s[mid - 1]! + s[mid]!) / 2;
}

/**
 * How a theme's factors did after the sample their papers studied.
 *
 * "Held" means the post-sample mean was still positive — JKP's own bar, which
 * asks whether the sign replicates, not whether the magnitude did. A factor
 * whose Sharpe halved still held; the median pair says how much it shrank.
 */
export function replication(rows: FactorRow[]): Replication {
  const both = rows.filter(
    (r) => r.in_sample?.sharpe != null && r.post_sample?.sharpe != null,
  );
  return {
    tested: both.length,
    held: both.filter((r) => (r.post_sample?.ann_return ?? 0) > 0).length,
    medianIn: median(both.map((r) => r.in_sample!.sharpe!)),
    medianPost: median(both.map((r) => r.post_sample!.sharpe!)),
  };
}

/** Signed percent with a real minus sign, e.g. "+2.9%" / "−1.4%". */
export function signedPct(x: number | null | undefined, digits = 1): string {
  if (x == null || !Number.isFinite(x)) return "—";
  const v = (x * 100).toFixed(digits);
  if (Number(v) === 0) return `${(0).toFixed(digits)}%`;
  return x > 0 ? `+${v}%` : `−${v.replace("-", "")}%`;
}

export function fixed(x: number | null | undefined, digits = 2): string {
  if (x == null || !Number.isFinite(x)) return "—";
  return x < 0 ? `−${Math.abs(x).toFixed(digits)}` : x.toFixed(digits);
}
