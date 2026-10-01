/**
 * The Regimes tab's types, colour jobs and small formatters.
 *
 * Shapes mirror `hedge_fund/regimes/detect.py` — `Analysis.as_dict()` is the
 * contract, and a field renamed there has to be renamed here.
 */

export type RegimeCentroid = {
  label: number;
  name: string;
  windows: number;
  share_pct: number | null;
  /** Annualised — a barycentre is a typical day, so a year of them is checkable. */
  mean_pct: number | null;
  /** The same centre as one day, for plotting against windows. */
  mean_day_pct: number | null;
  vol_pct: number | null;
  skew: number | null;
  kurtosis: number | null;
  worst_day_pct: number | null;
  best_day_pct: number | null;
  /** The centroid's own quantiles, 0 to 1 in 41 steps. It is a distribution. */
  quantiles: (number | null)[];
};

export type RegimeWindow = {
  start: string;
  end: string;
  label: number;
  /** The window's average day, in percent — not annualised. See detect.py. */
  mean_day_pct: number | null;
  vol_pct: number | null;
  skew: number | null;
  kurtosis: number | null;
  distance: number | null;
};

export type RegimeEpisode = {
  label: number;
  name: string;
  start: string;
  end: string;
  days: number;
};

export type RegimeVerdict = {
  within: (number | null)[];
  between: number | null;
  ratio: number | null;
  holds: boolean;
  sigma: number | null;
  draws: number;
  cluster_sizes: number[];
};

export type RegimeAnalysis = {
  ticker: string;
  params: { k: number; window_days: number; overlap_days: number; seed: number };
  coverage: {
    observations: number;
    first_date: string;
    last_date: string;
    windows: number;
  };
  fit: { inertia: number | null; iterations: number; converged: boolean };
  current: RegimeCentroid & { run_days: number };
  centroids: RegimeCentroid[];
  windows_detail: RegimeWindow[];
  episodes: RegimeEpisode[];
  path: {
    dates: string[];
    closes: (number | null)[];
    /** Share of covering windows calling that day stressed. `null` = unmeasured. */
    stress: (number | null)[];
  };
  validation: {
    wasserstein: RegimeVerdict;
    volatility_ratio: RegimeVerdict;
    /** Present when a hidden Markov model was also fitted — see `regimes/hmm.py`. */
    hmm?: RegimeVerdict | null;
    note: string;
  };
  caveats: string[];
  /**
   * The hidden-chain view, when fitted. Owned by `regimes/hmm.py` and rendered
   * elsewhere; declared optional here so this tab reads its separation score
   * without claiming to own the rest of the object.
   */
  hmm?: unknown;
};

/**
 * Colour by regime, calm to turbulent.
 *
 * Cobalt for calm and oxide for turbulent, which are the palette's two ends
 * and the two this app already uses for "structural" and "loss". Cadmium and
 * aluminium fill the middle when k is 3 or 4.
 *
 * Colour is never the only carrier: every chip, axis and tooltip that uses
 * these also prints the regime's name, per DESIGN.md.
 */
const RAMP = [
  "var(--cobalt)",
  "var(--verdigris)",
  "var(--cadmium)",
  "var(--oxide)",
] as const;

export function regimeColour(label: number, k: number): string {
  if (k <= 1) return RAMP[0];
  if (label <= 0) return RAMP[0];
  if (label >= k - 1) return RAMP[3];
  // Middle labels walk the ramp's interior in order, so k=3 reads cobalt →
  // verdigris → oxide and k=4 adds cadmium, with no two regimes sharing a
  // colour. Math.min guards a label beyond the ramp rather than reordering it.
  return RAMP[Math.min(2, label)];
}

/** A tint of the same colour, for area fills that must not fight the line. */
export function regimeTint(label: number, k: number, alpha = 0.16): string {
  return `color-mix(in oklab, ${regimeColour(label, k)} ${Math.round(alpha * 100)}%, transparent)`;
}

// ── formatters ────────────────────────────────────────────────────────────

export function pct(v: number | null | undefined, places = 1): string {
  return v == null || !Number.isFinite(v) ? "—" : `${v.toFixed(places)}%`;
}

export function signed(v: number | null | undefined, places = 1): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(places)}%`;
}

export function num(v: number | null | undefined, places = 2): string {
  return v == null || !Number.isFinite(v) ? "—" : v.toFixed(places);
}

/** "1 yr 4 mo" — trading days read as calendar time, which is how people think. */
export function spanWords(days: number): string {
  const months = Math.round((days / 252) * 12);
  if (months < 1) return `${days} trading days`;
  if (months < 18) return `${months} month${months === 1 ? "" : "s"}`;
  const y = Math.floor(months / 12);
  const m = months % 12;
  return m ? `${y} yr ${m} mo` : `${y} yr`;
}

export function shortDate(iso: string): string {
  const [y, m] = iso.split("-");
  const names = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ");
  return m ? `${names[Number(m) - 1]} ${y}` : iso;
}

/**
 * How to read a separation ratio, in words.
 *
 * The ratio is the only number on the tab that licenses believing the rest, so
 * it gets a verdict rather than being left as a decimal for the reader to
 * calibrate on their own. 1 is the hard line: at or below it the two groups
 * are one population cut in half.
 */
export function separationWord(ratio: number | null): {
  word: string;
  tone: "good" | "weak" | "bad" | "unknown";
} {
  /* Unmeasurable is its own tone, not "bad". A ratio the kernel could not
   * compute — one cluster too small to draw pairs from, a flat series — is
   * missing evidence, and colouring it oxide alongside a genuine failure
   * tells the reader the split was tested and lost. It was not tested. */
  if (ratio == null || !Number.isFinite(ratio)) return { word: "not measurable", tone: "unknown" };
  if (ratio >= 2) return { word: "clearly separated", tone: "good" };
  if (ratio > 1.3) return { word: "separated", tone: "good" };
  if (ratio > 1) return { word: "barely separated", tone: "weak" };
  return { word: "not separated", tone: "bad" };
}
