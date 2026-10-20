/**
 * "Is now the time?" — the memo's timing read, as plain arithmetic.
 *
 * Each signal is a reading the app already computes elsewhere (averages, RSI,
 * the 52-week range, peer value, the street target, the macro map, the
 * volatility regime) turned into one of three tones for someone about to buy.
 * The thresholds are conventions, not fitted values, and they are written here
 * so the memo can print them. Nothing here is the model's opinion.
 */

export type Tone = "go" | "wait" | "stop";
export type Signal = { label: string; reading: string; tone: Tone };
export type Quadrant = "goldilocks" | "overheating" | "recession" | "stagflation";

export type TimingInputs = {
  price: number | null;
  sma50?: number | null;
  sma200?: number | null;
  rsi?: number | null;
  low52?: number | null;
  high52?: number | null;
  compsMid?: number | null;
  streetTarget?: number | null;
  stockQuadrant?: Quadrant | null;
  nowQuadrant?: Quadrant | null;
  regime?: { name: string; days: number } | null;
};

const fin = (v: number | null | undefined): v is number =>
  typeof v === "number" && Number.isFinite(v);

/** Same rule as `hedge_fund.macro.sensitivity.quadrant`. */
export function quadrantOf(inflation: number, growth: number): Quadrant {
  if (growth >= 0) return inflation >= 0 ? "overheating" : "goldilocks";
  return inflation >= 0 ? "stagflation" : "recession";
}

const OPPOSITE: Record<Quadrant, Quadrant> = {
  goldilocks: "stagflation",
  stagflation: "goldilocks",
  overheating: "recession",
  recession: "overheating",
};

export function timingSignals(x: TimingInputs): Signal[] {
  const out: Signal[] = [];
  const p = x.price;

  if (fin(p) && fin(x.sma50) && fin(x.sma200)) {
    const above = [p > x.sma50, p > x.sma200].filter(Boolean).length;
    out.push({
      label: "Trend",
      reading:
        above === 2
          ? "Above its 50- and 200-day averages"
          : above === 0
            ? "Below its 50- and 200-day averages"
            : p > x.sma200
              ? "Above the 200-day, below the 50-day"
              : "Above the 50-day, below the 200-day",
      tone: above === 2 ? "go" : above === 0 ? "stop" : "wait",
    });
  }

  if (fin(x.rsi)) {
    const r = x.rsi;
    out.push({
      label: "Momentum",
      reading:
        r > 70
          ? `RSI ${r.toFixed(0)}, overbought: buying here is chasing`
          : r < 30
            ? `RSI ${r.toFixed(0)}, oversold: still falling, wait for a turn`
            : `RSI ${r.toFixed(0)}, neither stretched nor washed out`,
      tone: r > 70 ? "stop" : r < 30 ? "wait" : "go",
    });
  }

  if (fin(p) && fin(x.low52) && fin(x.high52) && x.high52 > x.low52) {
    const at = ((p - x.low52) / (x.high52 - x.low52)) * 100;
    out.push({
      label: "52-week range",
      reading: `${at.toFixed(0)}% of the way from the low to the high`,
      tone: at > 85 ? "stop" : at < 20 ? "wait" : "go",
    });
  }

  if (fin(p) && fin(x.compsMid)) {
    const gap = ((x.compsMid - p) / p) * 100;
    out.push({
      label: "Against peers",
      reading:
        gap >= 0
          ? `${gap.toFixed(0)}% below the peer-implied value`
          : `${(-gap).toFixed(0)}% above the peer-implied value`,
      tone: gap > 10 ? "go" : gap < -10 ? "stop" : "wait",
    });
  }

  if (fin(p) && fin(x.streetTarget)) {
    const up = ((x.streetTarget - p) / p) * 100;
    out.push({
      label: "Street target",
      reading: `${up >= 0 ? "+" : ""}${up.toFixed(0)}% to the analysts' average target`,
      tone: up > 15 ? "go" : up < 0 ? "stop" : "wait",
    });
  }

  if (x.stockQuadrant && x.nowQuadrant) {
    const s = x.stockQuadrant;
    const n = x.nowQuadrant;
    out.push({
      label: "Macro fit",
      reading:
        s === n
          ? `Does best in ${s}, and the last year has been ${n}`
          : `Does best in ${s}; the last year has been ${n}`,
      tone: s === n ? "go" : OPPOSITE[s] === n ? "stop" : "wait",
    });
  }

  if (x.regime) {
    const calm = x.regime.name === "calm";
    out.push({
      label: "Volatility regime",
      reading: `${calm ? "Calm" : "Turbulent"} for the last ${x.regime.days} trading days`,
      tone: calm ? "go" : "wait",
    });
  }

  return out;
}

/** One line over the signals. Needs at least three to say anything. */
export function timingVerdict(signals: Signal[]): { tone: Tone; text: string } | null {
  if (signals.length < 3) return null;
  const score =
    signals.filter((s) => s.tone === "go").length -
    signals.filter((s) => s.tone === "stop").length;
  if (score >= 2) return { tone: "go", text: "Conditions line up for acting now" };
  if (score <= -2) return { tone: "stop", text: "Conditions say wait" };
  return { tone: "wait", text: "Mixed: the case may be right, the timing is not clear" };
}
