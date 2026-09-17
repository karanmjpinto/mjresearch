import type { ScreenerUniverseMeta } from "@/lib/api";

/**
 * What to offer while `GET /screeners/universes` is in flight or unreachable.
 *
 * This list existed twice, inline, in the two screener panels, and both copies
 * still offered the NASDAQ-100, the Dow and the Russell 2000 — every one of
 * which stopped loading upstream (Wikipedia no longer renders the first two
 * tables into the page, and iShares serves HTML from the holdings-CSV
 * endpoint). A stale fallback is the worst kind: it puts three choices in the
 * dropdown that can only fail, and does it precisely when the server is not
 * answering and cannot correct it.
 *
 * So there is one copy, and it holds only universes that load. The server's
 * own list still wins whenever it arrives; this is the offline shape of it.
 */
export const FALLBACK_UNIVERSES: ScreenerUniverseMeta[] = [
  { id: "sp500", label: "S&P 500", description: "", approx_count: 503 },
  { id: "sp400", label: "S&P MidCap 400", description: "", approx_count: 400 },
  { id: "sp600", label: "S&P SmallCap 600", description: "", approx_count: 600 },
];

/**
 * Where each screen is pointed before anyone touches the controls.
 *
 * Not one shared default, because the screens disagree about what a candidate
 * is: the multi-bagger screen has a hard market-cap ceiling and passes
 * literally nothing in the S&P 500 — 502 of 503 names fail on size alone —
 * while the compounder wants the scale that serial acquirers operate at.
 * A single default would leave one of the two screens permanently empty.
 */
export const DEFAULT_UNIVERSE_FOR: Record<string, string> = {
  yartseva: "sp600",
  "acquisition-compounder": "sp500",
};
