import { describe, expect, it } from "vitest";

import { APP_HOME, SECTIONS, sectionByKey, sectionFor } from "./sections";

describe("SECTIONS", () => {
  it("offers exactly four doors at the top level", () => {
    expect(SECTIONS).toHaveLength(4);
  });

  it("numbers them in work order with no gaps", () => {
    expect(SECTIONS.map((s) => s.num)).toEqual(["01", "02", "03", "04"]);
  });

  it("gives every section and door a destination and a reason", () => {
    for (const s of SECTIONS) {
      expect(s.to.startsWith("/")).toBe(true);
      expect(s.question.length).toBeGreaterThan(0);
      for (const d of s.doors) {
        expect(d.to.startsWith("/")).toBe(true);
        expect(d.blurb.length).toBeGreaterThan(20);
      }
    }
  });
});

describe("sectionFor", () => {
  /**
   * The point of the section model is that being deep inside a flow still
   * lights the right door in the chrome. Standing on stage 05 of a company
   * is standing in Evaluate, not nowhere.
   */
  it.each([
    ["/find", "find"],
    ["/constraints", "find"],
    ["/screeners", "find"],
    ["/screeners/acquisition-compounder", "find"],
    ["/evaluate", "evaluate"],
    ["/research/AAPL", "evaluate"],
    ["/plan/AAPL", "evaluate"],
    ["/lens/BRK.B", "evaluate"],
    ["/value/7203.T", "evaluate"],
    ["/decide/AAPL", "evaluate"],
    ["/manage", "manage"],
    ["/dashboard", "manage"],
    ["/portfolio", "manage"],
    ["/autoresearch", "manage"],
    ["/breadth", "manage"],
    ["/optimize", "manage"],
    ["/setup", "setup"],
  ])("puts %s in the %s section", (path, key) => {
    expect(sectionFor(path)).toBe(key);
  });

  it("returns null outside the desk", () => {
    expect(sectionFor("/")).toBeNull();
    expect(sectionFor("/docs")).toBeNull();
    expect(sectionFor("/join")).toBeNull();
  });

  /**
   * Every live door must resolve to the section that lists it. A door added
   * to a section without a matching route entry would light the wrong tab,
   * and nothing else would catch that.
   */
  it("resolves every door back to its own section", () => {
    for (const s of SECTIONS) {
      for (const d of s.doors) {
        expect(sectionFor(d.to), `${d.to} in ${s.key}`).toBe(s.key);
      }
      expect(sectionFor(s.to), s.to).toBe(s.key);
    }
  });
});

describe("sectionByKey", () => {
  it("round-trips every key", () => {
    for (const s of SECTIONS) expect(sectionByKey(s.key)).toBe(s);
  });

  it("throws on an unknown key rather than returning undefined", () => {
    // @ts-expect-error — deliberately off the union
    expect(() => sectionByKey("nope")).toThrow(/unknown section/);
  });
});

describe("APP_HOME", () => {
  it("is a route inside the desk, so the catch-all cannot bounce forever", () => {
    expect(APP_HOME).toBe("/app");
  });
});
