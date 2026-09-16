import { describe, expect, it } from "vitest";
import {
  headlineField,
  isSigned,
  readField,
  unitFor,
  wordTone,
} from "./field-scales";

/**
 * A scale decides where a value is drawn between two stated endpoints. Get the
 * placement wrong and the track shows a different story from the digits beside
 * it — the reader believes the picture.
 */
describe("readField", () => {
  it("declines fields it has no reference range for", () => {
    // The documented fallback: unknown metrics render as plain text, so adding
    // a metric to the Python registry must not require touching this file.
    expect(readField("some_new_metric", 12)).toBeNull();
  });

  it("declines values that are not finite numbers", () => {
    expect(readField("conviction_score", null)).toBeNull();
    expect(readField("conviction_score", "80")).toBeNull();
    expect(readField("conviction_score", NaN)).toBeNull();
    expect(readField("conviction_score", Infinity)).toBeNull();
  });

  describe("score scales", () => {
    it("places the value linearly across the domain", () => {
      expect(readField("conviction_score", 80)?.at).toBeCloseTo(0.8, 10);
      expect(readField("valuation_score", 0)?.at).toBeCloseTo(0, 10);
      expect(readField("valuation_score", 100)?.at).toBeCloseTo(1, 10);
    });

    it("uses the same tone bands the conviction gauge does", () => {
      expect(readField("conviction_score", 75)?.tone).toBe("up");
      expect(readField("conviction_score", 74)?.tone).toBe("warn");
      expect(readField("conviction_score", 50)?.tone).toBe("warn");
      expect(readField("conviction_score", 49)?.tone).toBe("down");
    });

    it("anchors the origin at the left, since a score has no zero point", () => {
      expect(readField("conviction_score", 80)?.origin).toBe(0);
    });

    it("carries the endpoint labels the harness declared", () => {
      expect(readField("valuation_score", 50)?.ends).toEqual([
        "very expensive",
        "very cheap",
      ]);
    });
  });

  describe("signed scales", () => {
    it("puts the origin where zero actually falls", () => {
      // momentum_pct spans -100..100, so zero sits dead centre.
      expect(readField("momentum_pct", 10)?.origin).toBeCloseTo(0.5, 10);
    });

    it("places a value relative to the whole span, not to zero", () => {
      expect(readField("momentum_pct", 50)?.at).toBeCloseTo(0.75, 10);
      expect(readField("momentum_pct", -50)?.at).toBeCloseTo(0.25, 10);
    });

    it("reads the sign as the tone", () => {
      expect(readField("momentum_pct", 1)?.tone).toBe("up");
      expect(readField("momentum_pct", -1)?.tone).toBe("down");
      expect(readField("momentum_pct", 0)?.tone).toBe("neutral");
    });

    it("puts a drawdown's origin at the peak, since the domain ends at zero", () => {
      // max_drawdown_pct spans -80..0: 'at peak' is the right-hand end.
      const r = readField("max_drawdown_pct", -40);
      expect(r?.origin).toBeCloseTo(1, 10);
      expect(r?.at).toBeCloseTo(0.5, 10);
      expect(r?.ends).toEqual(["−80%", "at peak"]);
    });

    it("reports a unit where the field has one", () => {
      expect(readField("momentum_pct", 5)?.unit).toBe("%");
    });
  });

  describe("level scales", () => {
    it("has no favourable direction", () => {
      expect(readField("annualized_volatility_pct", 90)?.tone).toBe("neutral");
      expect(readField("annualized_volatility_pct", 5)?.tone).toBe("neutral");
    });
  });

  describe("multiple scales", () => {
    it("places log-scaled fields at the domain ends exactly", () => {
      expect(readField("pe_ratio", 4)?.at).toBeCloseTo(0, 10);
      expect(readField("pe_ratio", 120)?.at).toBeCloseTo(1, 10);
    });

    it("compresses the top of a log scale, which is the point of using one", () => {
      // Linear placement would put 62 near the middle; log keeps the crowded
      // low end legible instead.
      const mid = readField("pe_ratio", 62)?.at ?? 0;
      expect(mid).toBeGreaterThan(0.5);
    });

    it("calls a value inside the conventional band unremarkable", () => {
      expect(readField("pe_ratio", 10)?.tone).toBe("neutral");
      expect(readField("pe_ratio", 25)?.tone).toBe("neutral");
      expect(readField("pe_ratio", 9)?.tone).toBe("warn");
      expect(readField("pe_ratio", 26)?.tone).toBe("warn");
    });

    it("exposes the band in placed coordinates so it can be drawn", () => {
      const band = readField("pe_ratio", 15)?.band;
      expect(band).toHaveLength(2);
      expect(band![0]).toBeGreaterThan(0);
      expect(band![1]).toBeLessThan(1);
      expect(band![0]).toBeLessThan(band![1]);
    });
  });

  describe("out-of-domain values", () => {
    it("clamps the drawn position but says that it did", () => {
      // Silently pinning to the end would draw a 400 P/E identically to a 120.
      const r = readField("pe_ratio", 400);
      expect(r?.at).toBe(1);
      expect(r?.clamped).toBe(true);
    });

    it("clamps at the low end too", () => {
      const r = readField("momentum_pct", -500);
      expect(r?.at).toBe(0);
      expect(r?.clamped).toBe(true);
    });

    it("does not flag an in-domain value as clamped", () => {
      expect(readField("pe_ratio", 20)?.clamped).toBe(false);
      expect(readField("conviction_score", 100)?.clamped).toBe(false);
    });
  });
});

describe("unitFor / isSigned", () => {
  it("reports the unit only for fields that carry one", () => {
    expect(unitFor("momentum_pct")).toBe("%");
    expect(unitFor("pe_ratio")).toBe("×");
    expect(unitFor("conviction_score")).toBeUndefined();
    expect(unitFor("not_a_field")).toBeUndefined();
  });

  it("identifies zero-centred fields", () => {
    expect(isSigned("momentum_pct")).toBe(true);
    expect(isSigned("conviction_score")).toBe(false);
    expect(isSigned("not_a_field")).toBe(false);
  });
});

describe("headlineField", () => {
  it("picks the first field that has a scale", () => {
    expect(headlineField({ unknown_thing: 1, momentum_pct: 12 })).toBe(
      "momentum_pct",
    );
  });

  it("skips fields whose value cannot be placed", () => {
    expect(headlineField({ momentum_pct: null, conviction_score: 80 })).toBe(
      "conviction_score",
    );
  });

  it("returns null when nothing can be placed", () => {
    expect(headlineField({ a: 1, b: "x" })).toBeNull();
    expect(headlineField({})).toBeNull();
  });
});

describe("wordTone", () => {
  it("maps harness vocabulary to a tone", () => {
    expect(wordTone("cheap")).toBe("up");
    expect(wordTone("expensive")).toBe("down");
    expect(wordTone("elevated")).toBe("warn");
    expect(wordTone("fair")).toBe("neutral");
  });

  it("is insensitive to case and surrounding space", () => {
    expect(wordTone("  UpTrend  ")).toBe("up");
  });

  it("returns null for words it does not know", () => {
    expect(wordTone("spicy")).toBeNull();
  });
});
