/**
 * How to read a computed number.
 *
 * The plan returns bare fields — `pe_ratio 80.10`, `momentum_pct 48.28` — and a
 * bare number only means something to a reader who already carries its
 * reference range in their head. This module holds that reference range for
 * every field the metric registry can emit (`src/hedge_fund/plan/registry.py`),
 * so a view can place the value on a track instead of merely printing it.
 *
 * Two rules keep this honest:
 *
 * 1. **A scale is a domain, not advice.** It says where a value sits between
 *    two stated endpoints. Bands are conventional absolute ranges, carrying the
 *    same caveat the `valuation_score` metric states for itself: absolute, not
 *    sector-relative, and a low reading is not by itself a sell.
 * 2. **The words come from the harness.** Where a tone implies "favourable",
 *    it mirrors a direction the Python metric already declared — 100 is
 *    cheapest, 100 is strongest — rather than inventing one here.
 *
 * A field with no entry renders as plain text. That is the intended fallback:
 * new metrics stay readable without touching this file, and gain a track when
 * someone decides what its endpoints should be.
 */

export type Tone = "up" | "down" | "warn" | "neutral";

/**
 * - `score`    0–100 composite where the registry says high is favourable.
 * - `signed`   Centred on zero; the sign is the headline.
 * - `level`    A magnitude with no favourable direction.
 * - `multiple` Read against a conventional band rather than an endpoint.
 */
export type ScaleKind = "score" | "signed" | "level" | "multiple";

interface Scale {
  kind: ScaleKind;
  domain: [number, number];
  /** Conventional range, drawn as a band behind the track. */
  band?: [number, number];
  /**
   * Multiples are read multiplicatively — 80× is to 40× what 40× is to 20× —
   * so they are placed on a log axis. Without it every rich multiple pins to
   * the end of the track and stops being comparable to any other.
   */
  log?: boolean;
  unit?: string;
  /** What the two ends mean, when the numbers alone do not say it. */
  ends?: [string, string];
}

const PCT = "%";
const X = "×";

const SCALES: Record<string, Scale> = {
  /* Composite scores the harness defines as 100-is-best. */
  valuation_score: {
    kind: "score",
    domain: [0, 100],
    ends: ["very expensive", "very cheap"],
  },
  conviction_score: {
    kind: "score",
    domain: [0, 100],
    ends: ["strong sell", "strong buy"],
  },

  /* Zero-centred: the sign is the first thing worth knowing. */
  total_return_pct: { kind: "signed", domain: [-100, 100], unit: PCT },
  annualized_return_pct: { kind: "signed", domain: [-50, 50], unit: PCT },
  momentum_pct: { kind: "signed", domain: [-100, 100], unit: PCT },
  gap_to_sma_50_pct: { kind: "signed", domain: [-25, 25], unit: PCT },
  gap_to_sma_200_pct: { kind: "signed", domain: [-50, 50], unit: PCT },
  mean_signed: {
    kind: "signed",
    domain: [-1, 1],
    ends: ["negative", "positive"],
  },
  /* Drawdowns are reported as a decline, so the domain sits below zero and the
   * bar grows leftwards from the peak rather than up from nothing. */
  max_drawdown_pct: {
    kind: "signed",
    domain: [-80, 0],
    unit: PCT,
    ends: ["−80%", "at peak"],
  },
  current_drawdown_pct: {
    kind: "signed",
    domain: [-80, 0],
    unit: PCT,
    ends: ["−80%", "at peak"],
  },

  /* Magnitudes with no favourable direction. */
  annualized_volatility_pct: { kind: "level", domain: [0, 100], unit: PCT },
  recent_volatility_pct: { kind: "level", domain: [0, 100], unit: PCT },
  baseline_volatility_pct: { kind: "level", domain: [0, 100], unit: PCT },
  positive_day_pct: {
    kind: "level",
    domain: [0, 100],
    unit: PCT,
    ends: ["never up", "always up"],
  },
  range_position_pct: {
    kind: "level",
    domain: [0, 100],
    unit: PCT,
    ends: ["52w low", "52w high"],
  },
  pct_below_52w_high: { kind: "level", domain: [0, 60], unit: PCT },
  pct_above_52w_low: { kind: "level", domain: [0, 150], unit: PCT },

  /* Read against a conventional band. */
  pe_ratio: {
    kind: "multiple",
    domain: [4, 120],
    band: [10, 25],
    log: true,
    unit: X,
  },
  forward_pe: {
    kind: "multiple",
    domain: [4, 100],
    band: [10, 20],
    log: true,
    unit: X,
  },
  price_to_book: {
    kind: "multiple",
    domain: [0.3, 20],
    band: [1, 3],
    log: true,
    unit: X,
  },
  peg_ratio: {
    kind: "multiple",
    domain: [0.2, 5],
    band: [0.8, 1.5],
    log: true,
    unit: X,
  },
  beta: {
    kind: "multiple",
    domain: [0, 2.5],
    band: [0.8, 1.2],
    ends: ["unmoved", "2.5× market"],
  },
  sharpe_ratio: { kind: "multiple", domain: [-1, 3], band: [1, 3] },
  sortino_ratio: { kind: "multiple", domain: [-1, 4], band: [1, 4] },
  volatility_ratio: { kind: "multiple", domain: [0, 3], band: [0.8, 1.25] },
  rsi_14: {
    kind: "multiple",
    domain: [0, 100],
    band: [30, 70],
    ends: ["oversold", "overbought"],
  },
};

/** A value placed on its scale. All positions are fractions of the track, 0–1. */
export interface Reading {
  kind: ScaleKind;
  /** Where the value sits. */
  at: number;
  /** Where the bar grows from — zero for signed scales, the floor otherwise. */
  origin: number;
  /** The value ran past an endpoint and the track is showing the endpoint. */
  clamped: boolean;
  tone: Tone;
  /** The conventional band, as track fractions. */
  band?: [number, number];
  /** Labels for the two ends of the domain. */
  ends: [string, string];
  /** Human label for the band, e.g. `typical 10–25×`. */
  bandLabel?: string;
  unit?: string;
}

const clamp01 = (n: number) => Math.min(1, Math.max(0, n));

function place(v: number, s: Scale): number {
  const [lo, hi] = s.domain;
  if (s.log) {
    const safe = Math.max(v, 1e-6);
    return (Math.log(safe) - Math.log(lo)) / (Math.log(hi) - Math.log(lo));
  }
  return (v - lo) / (hi - lo);
}

function toneFor(v: number, s: Scale): Tone {
  switch (s.kind) {
    case "signed":
      return v > 0 ? "up" : v < 0 ? "down" : "neutral";
    case "score":
      /* The same bands ConvictionGauge uses, so a score means one thing across
       * the app rather than one thing per component. */
      return v >= 75 ? "up" : v >= 50 ? "warn" : "down";
    case "multiple":
      if (!s.band) return "neutral";
      return v >= s.band[0] && v <= s.band[1] ? "neutral" : "warn";
    default:
      return "neutral";
  }
}

function endLabel(v: number, s: Scale): string {
  return `${v}${s.unit ?? ""}`;
}

function bandLabel(s: Scale): string | undefined {
  if (!s.band) return undefined;
  return `typical ${s.band[0]}–${s.band[1]}${s.unit ?? ""}`;
}

/** Place a field's value on its scale, or `null` if the field has no scale. */
export function readField(name: string, value: unknown): Reading | null {
  const s = SCALES[name];
  if (!s || typeof value !== "number" || !Number.isFinite(value)) return null;

  const raw = place(value, s);
  const origin = s.kind === "signed" ? clamp01(place(0, s)) : 0;

  return {
    kind: s.kind,
    at: clamp01(raw),
    origin,
    clamped: raw < 0 || raw > 1,
    tone: toneFor(value, s),
    band: s.band
      ? [clamp01(place(s.band[0], s)), clamp01(place(s.band[1], s))]
      : undefined,
    ends: s.ends ?? [endLabel(s.domain[0], s), endLabel(s.domain[1], s)],
    bandLabel: bandLabel(s),
    unit: s.unit,
  };
}

/** The unit a field carries, whether or not it has a full scale. */
export function unitFor(name: string): string | undefined {
  return SCALES[name]?.unit;
}

/** True when the field's sign is the headline and should always be printed. */
export function isSigned(name: string): boolean {
  return SCALES[name]?.kind === "signed";
}

/**
 * The field a node leads with: the first one the harness emitted that has a
 * scale. Registry field order is the metric author's own ordering, so this
 * follows their judgement instead of hardcoding a metric-to-field table that
 * would go stale the moment a metric is added.
 */
export function headlineField(values: Record<string, unknown>): string | null {
  for (const [k, v] of Object.entries(values)) {
    if (readField(k, v)) return k;
  }
  return null;
}

/**
 * Categorical words the harness itself uses, mapped to a tone. Nothing is
 * invented here — `cheap`, `uptrend` and `elevated` are the metric's own
 * vocabulary, given a colour so the eye can sort them.
 */
const WORD_TONE: Record<string, Tone> = {
  cheap: "up",
  fair: "neutral",
  expensive: "down",
  uptrend: "up",
  downtrend: "down",
  unknown: "neutral",
  positive: "up",
  neutral: "neutral",
  negative: "down",
  elevated: "warn",
  normal: "neutral",
  subdued: "neutral",
};

export function wordTone(value: string): Tone | null {
  return WORD_TONE[value.trim().toLowerCase()] ?? null;
}
