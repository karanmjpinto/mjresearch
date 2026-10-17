/**
 * The four things you can be doing at this desk, and nothing else.
 *
 * The app had fifteen routes behind one "Other ▾" menu and a six-stage rail.
 * Every screen was reachable, which is not the same as the desk being
 * legible: the menu listed a screener, a dashboard and a setup page as
 * siblings, so the first decision a user made each session was "which of
 * these nine words is the thing I want", and that question has no good
 * answer. `flow.ts` had already fixed this *within* one company — one
 * subject, one path. This module does the same thing one level up.
 *
 * The split is by **what you are trying to do**, not by what the screen
 * contains:
 *
 *   find       I do not have a name yet. Give me candidates.
 *   evaluate   I have a name. Is it worth owning, and how much?
 *   manage     I own things. What do I hold, by what rules, and what changed?
 *   setup      The desk itself — keys, providers, the model.
 *
 * Those are mutually exclusive and jointly exhaustive for this desk, which is
 * the property that makes a top-level menu worth having. A fifth entry would
 * mean one of the four is wrong.
 *
 * **Every existing route still resolves.** This is a new front door, not a
 * renaming: `/screeners`, `/dashboard`, `/plan/AAPL` and the rest are
 * untouched and keep every inbound link working. What changes is where you
 * land and what the chrome offers you — which is the whole of the problem
 * being solved.
 */

export type SectionKey = "find" | "evaluate" | "manage" | "setup";

/** One choice inside a section. A section with no doors is a screen itself. */
export type Door = {
  to: string;
  label: string;
  /**
   * What this door is *for*, in the user's words, not the screen's. "Start
   * from a constraint the market has mispriced" rather than "Constraints
   * view". The label names the destination; this says why you would pick it.
   */
  blurb: string;
  /**
   * `planned` doors render greyed with their intent visible and are not
   * clickable. They exist so the shape of the desk is honest about what is
   * not built yet — a menu that silently omits the gap teaches you the gap
   * is not coming.
   */
  status: "live" | "planned";
};

export type Section = {
  key: SectionKey;
  /** The sequence is the order of the work, and it is information. */
  num: string;
  label: string;
  /** The single question this section answers, in the first person. */
  question: string;
  /** Where the section itself lives. */
  to: string;
  doors: readonly Door[];
};

export const SECTIONS: readonly Section[] = [
  {
    key: "find",
    num: "01",
    label: "Find opportunities",
    question: "I don't have a name yet.",
    to: "/find",
    doors: [
      {
        to: "/constraints",
        label: "From a constraint",
        blurb:
          "Start from something structural the market has to price — a binding limit, not a story — and work out who it hurts and who it pays.",
        status: "live",
      },
      {
        to: "/screeners",
        label: "From a screen",
        blurb:
          "Six scored screens over sixteen universes. Quality compounders, multibaggers, the Japan handbook, two-act turnarounds, and who the AI buyers are shopping for.",
        status: "live",
      },
    ],
  },
  {
    key: "evaluate",
    num: "02",
    label: "Evaluate an opportunity",
    question: "I have a name. Is it worth owning, and how much?",
    to: "/evaluate",
    /* No doors: this section IS the six-stage flow in `flow.ts`, and the
     * entry to it is picking a symbol. Listing the stages here would make
     * them look like six independent choices, which is exactly the framing
     * the stage rail exists to replace — they are one path, run in order. */
    doors: [],
  },
  {
    key: "manage",
    num: "03",
    label: "Manage the portfolio",
    question: "What do I hold, by what rules, and what changed?",
    to: "/manage",
    doors: [
      {
        to: "/dashboard",
        label: "Dashboard",
        blurb:
          "The glance: open work, recent runs and decisions, watchlists, where the market is.",
        status: "live",
      },
      {
        to: "/portfolio",
        label: "Positions",
        blurb:
          "What is actually held, what it cost, what it is worth, and how concentrated the book has become.",
        status: "live",
      },
      {
        to: "/principles",
        label: "Principles",
        blurb:
          "The rules the desk runs by — where it will look, what it will not own, the bars it enforces, and the judgments it admits it cannot compute.",
        status: "planned",
      },
      {
        to: "/autoresearch",
        label: "Autoresearch",
        blurb:
          "The desk working while you are not at it: queue names, let the committee run, read the reports when they land.",
        status: "live",
      },
    ],
  },
  {
    key: "setup",
    num: "04",
    label: "Set up",
    question: "Keys, providers, and the model doing the writing.",
    to: "/setup",
    doors: [],
  },
] as const;

/* Routes that belong to a section but are not one of its doors. Used to
 * light the right section in the chrome when you are deep inside one —
 * standing on `/plan/AAPL` is standing in Evaluate. */
const EXTRA_ROUTES: Readonly<Record<string, SectionKey>> = {
  research: "evaluate",
  plan: "evaluate",
  lens: "evaluate",
  value: "evaluate",
  decide: "evaluate",
  capture: "evaluate",
  breadth: "manage",
  optimize: "manage",
};

const BY_FIRST_SEGMENT = new Map<string, SectionKey>([
  ...SECTIONS.flatMap((s) => {
    const own: [string, SectionKey][] = [[first(s.to), s.key]];
    return own.concat(s.doors.map((d) => [first(d.to), s.key]));
  }),
  ...Object.entries(EXTRA_ROUTES),
]);

function first(path: string): string {
  return path.replace(/^\/+/, "").split("/")[0]!.toLowerCase();
}

/**
 * Which section a path belongs to, or null for anything outside the desk
 * (the landing, the reference, the join screen).
 *
 * Matching on the first segment only, so `/plan/AAPL` and a bare `/plan`
 * both resolve to Evaluate — the section is the section before a symbol is
 * chosen.
 */
export function sectionFor(pathname: string): SectionKey | null {
  const seg = first(pathname);
  if (!seg) return null;
  return BY_FIRST_SEGMENT.get(seg) ?? null;
}

export function sectionByKey(key: SectionKey): Section {
  const found = SECTIONS.find((s) => s.key === key);
  if (!found) throw new Error(`unknown section: ${key}`);
  return found;
}

/** Where the app opens. One place, so the landing and the catch-all agree. */
export const APP_HOME = "/app";
