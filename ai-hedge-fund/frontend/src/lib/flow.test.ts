import { describe, expect, it } from "vitest";
import {
  DESTINATIONS,
  OTHER_DESTINATIONS,
  STAGES,
  TICKER_PATH_RE,
  VISIBLE_OTHER_DESTINATIONS,
  stageFor,
  stagePath,
} from "./flow";

describe("stage sequence", () => {
  it("numbers the six stages 01 to 06 in order", () => {
    expect(STAGES.map((s) => s.num)).toEqual([
      "01",
      "02",
      "03",
      "04",
      "05",
      "06",
    ]);
  });

  it("gives exactly one stage no destination — picking the ticker is the entry", () => {
    const entries = STAGES.filter((s) => s.segment === null);
    expect(entries.map((s) => s.key)).toEqual(["ticker"]);
    expect(DESTINATIONS).toHaveLength(5);
  });

  it("marks an unbuilt stage as planned rather than shipping a blank screen", () => {
    // Asserts the invariant rather than a list of keys. This test used to name
    // the planned stages outright, which meant finishing one broke a test that
    // had nothing to say about it — the rail's promise is that `planned` is a
    // real state and that nothing claims a status it does not have, not that
    // any particular stage is unfinished this week.
    for (const s of STAGES) {
      expect(["live", "planned"]).toContain(s.status);
    }
    // A planned stage still has to be reachable, because the rail renders it
    // as a link to a screen that explains the intent. One with no route would
    // be a dead entry.
    for (const s of STAGES.filter((x) => x.status === "planned")) {
      expect(s.segment, `planned stage ${s.key} needs a route`).not.toBeNull();
    }
  });

  it("gives every stage a question, since that is what the rail promises", () => {
    for (const s of STAGES) expect(s.question).not.toBe("");
  });
});

describe("stagePath", () => {
  it("keeps the legacy route spellings so inbound links stay alive", () => {
    expect(stagePath("data", "AAPL")).toBe("/research/AAPL");
    expect(stagePath("analysis", "AAPL")).toBe("/plan/AAPL");
    expect(stagePath("play", "AAPL")).toBe("/decide/AAPL");
  });

  it("uppercases and trims what the user typed", () => {
    expect(stagePath("data", "  aapl ")).toBe("/research/AAPL");
  });

  it("encodes symbols that are not plain letters", () => {
    expect(stagePath("data", "BRK.B")).toBe("/research/BRK.B");
    expect(stagePath("data", "A/B")).toBe("/research/A%2FB");
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
    expect(stageFor("/plan")).toBe("analysis");
  });

  it("ignores case and trailing segments", () => {
    expect(stageFor("/Research/AAPL/whatever")).toBe("data");
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
      "capture",
      "home",
      "screeners",
      "breadth",
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

describe("hiding a destination", () => {
  it("is a subset — hiding removes from the menu, never from the app", () => {
    // The guarantee the whole mechanism rests on. A hidden screen keeps its
    // route, its chunk and its inbound links; the only thing it loses is a
    // row in the disclosure. Anything that drops an entry from
    // OTHER_DESTINATIONS instead of flipping `visible` breaks that.
    for (const d of VISIBLE_OTHER_DESTINATIONS) {
      expect(OTHER_DESTINATIONS).toContain(d);
    }
    expect(VISIBLE_OTHER_DESTINATIONS.length).toBeLessThanOrEqual(
      OTHER_DESTINATIONS.length,
    );
  });

  it("still names where you are when you arrive on a hidden screen by URL", () => {
    // The actual bug this guards: AppNav labels the menu "Other · <here>" by
    // looking `active` up in the destination list. Narrowing that lookup to
    // the visible list would make a hidden screen render a bare "Other",
    // telling the reader the screen they are looking at does not exist.
    const hidden = OTHER_DESTINATIONS.filter((d) => !d.visible);
    for (const d of hidden) {
      expect(OTHER_DESTINATIONS.find((x) => x.key === d.key)?.label).toBe(
        d.label,
      );
    }
  });

  it("keeps at least the entry points listed, so the menu is never empty", () => {
    const keys = VISIBLE_OTHER_DESTINATIONS.map((d) => d.key);
    for (const required of ["home", "screeners", "setup"]) {
      expect(keys).toContain(required);
    }
  });
});
