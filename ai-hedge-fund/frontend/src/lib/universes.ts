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
  {
    id: "sp600",
    label: "S&P SmallCap 600",
    description: "",
    approx_count: 600,
  },
  {
    id: "jp_mid_small",
    label: "Japan mid & small",
    description: "",
    approx_count: 874,
  },
  { id: "uk_mid", label: "UK mid (FTSE 250)", description: "", approx_count: 250 },
  { id: "de_mid", label: "Germany mid (MDAX)", description: "", approx_count: 50 },
  {
    id: "ca_all",
    label: "Canada (TSX operating cos)",
    description: "",
    approx_count: 800,
  },
  {
    id: "au_all",
    label: "Australia (ASX listed)",
    description: "",
    approx_count: 1900,
  },
];

/**
 * Where each screen is pointed before anyone touches the controls.
 *
 * Not one shared default, because the screens disagree about what a candidate
 * is: the multi-bagger screen has a hard market-cap ceiling and passes
 * literally nothing in the S&P 500 — 502 of 503 names fail on size alone.
 *
 * The compounder used to default to the S&P 500, and that one line was the
 * only thing making it a large-cap screen: it had no market-cap filter at all,
 * while every test it runs — return on capital above 12%, cash conversion
 * above 80%, a share count that does not grow — applies at any size. It now
 * carries an explicit small and mid-cap band, so it is pointed at the mid-cap
 * index, which is the band that band describes and the one universe no screen
 * previously landed on.
 */
export const DEFAULT_UNIVERSE_FOR: Record<string, string> = {
  yartseva: "sp600",
  "acquisition-compounder": "sp400",
  "bolton-contrarian": "sp500",
  /* Not a preference. Kiyohara's checklist reads a Japanese shareholder
   * register and a yen market cap; run over the S&P 500 it would still return
   * names, which is worse than returning none. */
  "kiyohara-handbook": "jp_mid_small",
  /* His own study: roughly 80% of the companies that compound at 20% for a
   * decade start that run as small caps, between about $1bn and $6bn. The
   * SmallCap 600 is that shelf. */
  "ellenbogen-two-act": "sp600",
};
