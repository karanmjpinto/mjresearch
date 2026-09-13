import { describe, expect, it } from "vitest";
import {
  DESTINATIONS,
  OTHER_DESTINATIONS,
  STAGES,
  TICKER_PATH_RE,
  stageFor,
  stagePath,
} from "./flow";

describe("stage sequence", () => {
  it("numbers the six stages 01 to 06 in order", () => {
    expect(STAGES.map((s) => s.num)).toEqual(["01", "02", "03", "04", "05", "06"]);
  });

  it("gives exactly one stage no destination — picking the ticker is the entry", () => {
    const entries = STAGES.filter((s) => s.segment === null);
    expect(entries.map((s) => s.key)).toEqual(["ticker"]);
    expect(DESTINATIONS).toHaveLength(5);
  });

  it("marks an unbuilt stage as planned rather than shipping a blank screen", () => {
    // Stage 04 became live when the vault reader landed; 05 is still partial,
    // so the rail keeps saying so rather than promising a finished screen.
    const planned = STAGES.filter((s) => s.status === "planned").map((s) => s.key);
    expect(planned).toEqual(["value"]);
  });

  it("gives every stage a question, since that is what the rail promises", () => {
    for (const s of STAGES) expect(s.question).not.toBe("");
  });
});

describe("stagePath", () => {
  it("keeps the legacy route spellings so inbound links stay alive", () => {
    expect(stagePath("story", "AAPL")).toBe("/research/AAPL");
    expect(stagePath("numbers", "AAPL")).toBe("/plan/AAPL");
    expect(stagePath("play", "AAPL")).toBe("/decide/AAPL");
  });

  it("uppercases and trims what the user typed", () => {
    expect(stagePath("story", "  aapl ")).toBe("/research/AAPL");
  });

  it("encodes symbols that are not plain letters", () => {
    expect(stagePath("story", "BRK.B")).toBe("/research/BRK.B");
    expect(stagePath("story", "A/B")).toBe("/research/A%2FB");
  });

  it("falls back to the bare stage when there is no symbol yet", () => {
    expect(stagePath("play", "")).toBe("/decide");
  });
});

describe("stageFor", () => {
  it("round-trips every destination stage", () => {
    for (const s of DESTINATIONS) {
      expect(stageFor(stagePath(s.key, "AAPL"))).toBe(s.key);
    }
  });

  it("resolves a stage with no symbol attached", () => {
    expect(stageFor("/plan")).toBe("numbers");
  });

  it("ignores case and trailing segments", () => {
    expect(stageFor("/Research/AAPL/whatever")).toBe("story");
  });

  it("returns null off the flow, so the rail stays hidden there", () => {
    for (const p of ["/", "/dashboard", "/portfolio", "/setup", ""]) {
      expect(stageFor(p)).toBeNull();
    }
  });
});

describe("TICKER_PATH_RE", () => {
  it("pulls the symbol back out of a flow route", () => {
    expect("/research/AAPL".match(TICKER_PATH_RE)?.[2]).toBe("AAPL");
    expect("/value/BRK.B".match(TICKER_PATH_RE)?.[2]).toBe("BRK.B");
  });

  it("covers the new stages, which the old hardcoded pattern did not", () => {
    expect(TICKER_PATH_RE.test("/lens/AAPL")).toBe(true);
    expect(TICKER_PATH_RE.test("/value/AAPL")).toBe(true);
  });

  it("does not match off-flow routes", () => {
    expect(TICKER_PATH_RE.test("/portfolio")).toBe(false);
  });
});

describe("other destinations", () => {
  it("holds the screens off the flow, with the no-ticker way in first", () => {
    // "constraints" leads because it is the only entry point here: everything
    // below it is a destination you go to, and that one is where you start
    // when you have no symbol yet.
    expect(OTHER_DESTINATIONS.map((d) => d.key)).toEqual([
      "constraints",
      "home",
      "screeners",
      "portfolio",
      "optimize",
      "autoresearch",
      "setup",
    ]);
  });

  it("never lists a stage route, or the menu would compete with the rail", () => {
    const segments = DESTINATIONS.map((s) => `/${s.segment}`);
    for (const d of OTHER_DESTINATIONS) expect(segments).not.toContain(d.to);
  });
});
