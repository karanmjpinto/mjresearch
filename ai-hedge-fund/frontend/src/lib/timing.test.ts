import { describe, expect, it } from "vitest";
import { quadrantOf, timingSignals, timingVerdict } from "./timing";

describe("timingSignals", () => {
  it("reads STRL's October 2026 state as a downtrend at a discount to the street", () => {
    const s = timingSignals({
      price: 412.25,
      sma50: 501.48,
      sma200: 549.6,
      rsi: 33.67,
      low52: 281.58,
      high52: 1005.68,
      compsMid: 355.69,
      streetTarget: 836.71,
      stockQuadrant: "goldilocks",
      nowQuadrant: "stagflation",
      regime: { name: "turbulent", days: 252 },
    });
    const tones = Object.fromEntries(s.map((x) => [x.label, x.tone]));
    expect(tones).toEqual({
      Trend: "stop",
      Momentum: "go",
      "52-week range": "wait",
      "Against peers": "stop",
      "Street target": "go",
      "Macro fit": "stop",
      "Volatility regime": "wait",
    });
    expect(timingVerdict(s)?.tone).toBe("wait");
  });

  it("skips what it cannot read rather than guessing", () => {
    expect(timingSignals({ price: null, rsi: 50 })).toHaveLength(1);
    expect(timingVerdict(timingSignals({ price: 10, rsi: 50 }))).toBeNull();
  });

  it("names quadrants the way the backend does", () => {
    expect(quadrantOf(-0.1, 0.2)).toBe("goldilocks");
    expect(quadrantOf(0.1, 0.2)).toBe("overheating");
    expect(quadrantOf(0.1, -0.2)).toBe("stagflation");
    expect(quadrantOf(-0.1, -0.2)).toBe("recession");
  });
});
