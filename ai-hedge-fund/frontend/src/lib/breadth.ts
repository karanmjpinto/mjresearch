/**
 * Shapes and small helpers for the market-breadth screen.
 *
 * Mirrors `hedge_fund/api/routes/breadth.py`. Kept out of `api.ts` for the
 * same reason `regimes.ts` is: the formatters belong next to the types they
 * format, not three hundred lines away from them.
 */

export type BreadthSummary = {
  median: number | null;
  hit_rate: number | null;
  n: number;
};

export type BreadthHorizon = {
  after_divergence: BreadthSummary;
  unconditional: BreadthSummary;
};

export type BreadthEpisode = {
  start: string;
  end: string;
  days: number;
  index_gap_pct: number;
  pct_above_at_start: number;
  forward: Record<string, number | null>;
};

export type BreadthReading = {
  date: string;
  members: number;
  index_gap_pct: number;
  pct_above_200dma: number;
  net_new_highs_pct: number;
  ad_line_peak_date: string;
  days_since_ad_peak: number;
  divergent: boolean;
};

export type BreadthResponse = {
  reading: BreadthReading;
  episodes: BreadthEpisode[];
  base_rates: Record<string, BreadthHorizon>;
  thresholds: { near: number; floor: number; gap_days: number };
  coverage: {
    first_session: string;
    last_session: string;
    sessions: number;
    signal_days: number;
    episodes: number;
  };
  verdict: {
    stance: "confirmed" | "contradicted" | "no-signal" | "untested";
    line: string;
    episodes?: number;
  };
  series: {
    dates: string[];
    ad_line: (number | null)[];
    pct_above_200dma: (number | null)[];
    net_new_highs_pct: (number | null)[];
    index: (number | null)[];
  };
  source: {
    universe: string;
    index_symbol: string;
    built_at: string;
    age_days: number;
    stale: boolean;
    refresh: string;
  };
  limits: { title: string; body: string }[];
};

/** Horizons in the order they are read, with the words a reader uses. */
export const HORIZONS = [
  { key: "63d", label: "3 months" },
  { key: "126d", label: "6 months" },
  { key: "252d", label: "1 year" },
] as const;

export const pct1 = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? "—" : `${v.toFixed(1)}%`;

export const signed1 = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;

export const shortDate = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });

/**
 * The colour a verdict is allowed to use.
 *
 * `contradicted` is deliberately not red. It does not mean something is wrong;
 * it means the warning did not pay in this sample, which is a finding like any
 * other. Red here would editorialise a result into a failure.
 */
export const stanceTone: Record<BreadthResponse["verdict"]["stance"], string> = {
  confirmed: "text-oxide",
  contradicted: "text-verdigris",
  "no-signal": "text-on-ink-soft",
  untested: "text-on-ink-soft",
};
