/**
 * The six stages of looking at one company, in the order the work runs.
 *
 * The app was nine destinations with a three-stage bar underneath, which left
 * one question — is this worth owning, and how much — spread across screens
 * that each answered a fragment of it. This module is the spine that replaces
 * that: one subject, one path, and everything not about a single company moved
 * off the path into `OTHER_DESTINATIONS`.
 *
 * Stage paths deliberately keep the legacy `/research`, `/plan` and `/decide`
 * spellings. Renaming them would break every inbound link in the dashboard,
 * the screeners and the compounder panels in exchange for nothing a reader can
 * see: the rail is what changes how this feels, not the URL.
 *
 * Stages 02 and 03 were "Story" and "Numbers", which described neither. The
 * Story screen was charts, ownership and backtests — quantitative to the last
 * row — while the numbers the model actually reasoned over sat on the next
 * screen beside prose. The split is now by *kind of evidence*: stage 02 is
 * everything measured, stage 03 is everything judged. That is a line a reader
 * can hold, and it puts the investor views next to the analysis that weighs
 * them rather than two clicks apart.
 */

export type StageKey =
  "ticker" | "data" | "analysis" | "lens" | "value" | "play";

/** Stages with a screen of their own — every key except the entry step. */
export type DestinationKey = Exclude<StageKey, "ticker">;

export type Stage = {
  key: StageKey;
  /** The sequence is information, not decoration: each stage feeds the next. */
  num: string;
  label: string;
  /** The single question the stage exists to answer. */
  question: string;
  /**
   * `null` marks the entry step. Picking a ticker is stage 01, so it has no
   * destination — it is satisfied the moment a symbol is active, which is why
   * the rail renders it as the symbol itself rather than as a link to nowhere.
   */
  segment: string | null;
  /** `planned` stages render their intent. They must never look broken. */
  status: "live" | "planned";
};

export const STAGES: readonly Stage[] = [
  {
    key: "ticker",
    num: "01",
    label: "Ticker",
    question: "Which company?",
    segment: null,
    status: "live",
  },
  {
    key: "data",
    num: "02",
    label: "Data",
    question: "What does the data say?",
    segment: "research",
    status: "live",
  },
  {
    key: "analysis",
    num: "03",
    label: "Analysis",
    question: "What do the model and the investors make of it?",
    segment: "plan",
    status: "live",
  },
  {
    key: "lens",
    num: "04",
    label: "Your lens",
    question: "What do I already know here?",
    segment: "lens",
    status: "live",
  },
  {
    key: "value",
    num: "05",
    label: "Value & risk",
    question: "What's it worth, and how sure can I be?",
    segment: "value",
    status: "live",
  },
  {
    key: "play",
    num: "06",
    label: "Play it",
    question: "How to express it, and how big?",
    segment: "decide",
    status: "live",
  },
] as const;

/** A stage you can actually navigate to: it has a route and is not the entry. */
export type DestinationStage = Stage & { key: DestinationKey; segment: string };

/**
 * Stages that have a route, in flow order.
 *
 * Narrowing `key` as well as `segment` is what lets callers pass a stage
 * straight to `stagePath` or `goTo`. Without it every call site has to re-prove
 * that the entry step is not in this list, which the filter already guarantees.
 */
export const DESTINATIONS: readonly DestinationStage[] = STAGES.filter(
  (s): s is DestinationStage => s.segment !== null,
);

const BY_SEGMENT = new Map(DESTINATIONS.map((s) => [s.segment, s.key]));

/**
 * The route for a stage. Symbols are encoded because tickers are not all
 * `[A-Z]`: share classes carry dots, and foreign listings carry suffixes.
 */
export function stagePath(key: DestinationKey, ticker: string): string {
  const stage = DESTINATIONS.find((s) => s.key === key);
  if (!stage) throw new Error(`unknown stage: ${key}`);
  const clean = ticker.trim().toUpperCase();
  return clean
    ? `/${stage.segment}/${encodeURIComponent(clean)}`
    : `/${stage.segment}`;
}

/**
 * Which stage a path belongs to, or null for anything off the flow.
 *
 * Matching on the first segment only, so `/plan/AAPL` and a bare `/plan` both
 * resolve — the stage is still the stage before a symbol is chosen.
 */
export function stageFor(pathname: string): StageKey | null {
  const first = pathname.replace(/^\/+/, "").split("/")[0]?.toLowerCase();
  // An empty first segment is the root, not a stage. Returning it would hand
  // callers an empty string where they are checking for null.
  if (!first) return null;
  return BY_SEGMENT.get(first) ?? null;
}

/** Matches a flow route carrying a symbol, for pulling the symbol back out. */
export const TICKER_PATH_RE = new RegExp(
  `^/(${DESTINATIONS.map((s) => s.segment).join("|")})/([^/?#]+)`,
  "i",
);

/**
 * Everything that is not about one company. These keep working untouched; they
 * just stop competing for attention with the flow.
 */
export const OTHER_DESTINATIONS: readonly {
  to: string;
  key: string;
  label: string;
}[] = [
  { to: "/constraints", key: "constraints", label: "Find a constraint" },
  { to: "/dashboard", key: "home", label: "Dashboard" },
  { to: "/screeners", key: "screeners", label: "Screeners" },
  { to: "/portfolio", key: "portfolio", label: "Portfolio" },
  { to: "/optimize", key: "optimize", label: "Optimize" },
  { to: "/autoresearch", key: "autoresearch", label: "Autoresearch" },
  { to: "/setup", key: "setup", label: "Setup" },
] as const;
