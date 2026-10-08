/**
 * Screener definitions and sample rows. Replace `plays` with API data or extend criteria per view.
 */
export type ScreenerPlay = {
  ticker: string;
  setup: string;
  entry: string;
  stop?: string;
  target?: string;
  /** Suggested allocation as % of book (0–100). */
  sizePct?: number;
  sizeNotes?: string;
  notes?: string;
};

export type ScreenerCriteriaSection = {
  title: string;
  items: string[];
};

export type ScreenerViewDef = {
  id: string;
  label: string;
  description: string;
  /** Screening intent — swap for your real filters / signals. */
  criteria: string[];
  /** When set, the UI shows grouped sections instead of a flat bullet list. */
  criteriaSections?: ScreenerCriteriaSection[];
  plays: ScreenerPlay[];
  /** When true, the UI runs the backend screener instead of static plays. */
  usesApi?: boolean;
  /**
   * The backend screen name, when it differs from `id`.
   *
   * These two drifted apart early (`acquisition_compounder` here,
   * `acquisition-compounder` on the wire) and the view resolved it with a
   * ternary — fine for two screens, wrong the moment a third exists, because
   * the `else` silently claimed every new screen was the compounder. Carrying
   * the real name as data makes adding a screen a row rather than a branch.
   */
  screenId?:
    | "yartseva"
    | "acquisition-compounder"
    | "bolton-contrarian"
    | "kiyohara-handbook";
  /** Highest attainable score, for the result bars. */
  scoreMax?: number;
  /** Glossary term for the results heading. */
  infoTerm?:
    | "screen-yartseva"
    | "screen-acquisition"
    | "screen-bolton"
    | "screen-kiyohara";
  /** Heading and blurb for the pre-computed results panel. */
  resultsTitle?: string;
  resultsBlurb?: string;
};

export const SCREENER_VIEWS: ScreenerViewDef[] = [
  {
    id: "yartseva",
    screenId: "yartseva",
    scoreMax: 100,
    infoTerm: "screen-yartseva",
    resultsTitle: "S&P SmallCap 600, ranked by the multibagger composite",
    resultsBlurb:
      "Already run across the small-cap index — the size band where a company can still multiply several times over. Every name here cleared the hard filters; the bar is its composite out of 100.",
    label: "Yartseva Multibagger",
    description:
      "Paper-based multibagger model: hard filters (cap, profitability, balance sheet, sector), then weighted composite (FCF yield, book/market value, ROA, investment quality, size, entry timing). Data via yfinance — verify against filings.",
    usesApi: true,
    criteria: [
      "Stage 1 (all required): $50M < market cap < $2B; EBITDA > 0; operating margin > 0; FCF > 0; book equity > 0; YoY total assets growth > 0; sector not Financials/Utilities",
      "Stage 2 weights: FCF yield 30%, B/M value 25%, ROA profitability 15%, investment quality 15%, size 10%, entry timing 5%",
      "Tiers: 75+ strong, 55–74 watch, 35–54 borderline, <35 fail",
      "Short-sell flag when equity ≤ 0, margin < 0, cap < $200M, and assets shrinking (independent check)",
      "Macro regime (Fed) is portfolio-level — see results note after running",
    ],
    plays: [],
  },
  {
    id: "acquisition_compounder",
    screenId: "acquisition-compounder",
    scoreMax: 45,
    infoTerm: "screen-acquisition",
    resultsTitle: "S&P 500, ranked by the compounder score",
    resultsBlurb:
      "Already run across the index. Every name here cleared the hard filters; the bar is its nine-factor score out of 45.",
    label: "Acquisition Compounder",
    description:
      "Automated from yfinance: growth, ROIC, FCF conversion, leverage, margin trends, dilution, industry avoid-list, 9-factor score (/45), optional quality tier. Short history uses span CAGR / info fallbacks — verify in filings.",
    usesApi: true,
    criteria: [
      "Hard filters: revenue & EPS/FCF-per-share growth, revenue YoY proxy >3%, ROIC, FCF/NI, margin trends, net debt/EBITDA, interest coverage, share CAGR, goodwill impairment heuristic",
      "Tier 2 (optional): stricter growth/ROIC/FCF margin/FCF-ps vs revenue / leverage",
      "Score tiers: 35+ strong, 40+ elite (weak below 28)",
    ],
    plays: [],
  },
  {
    id: "bolton_contrarian",
    screenId: "bolton-contrarian",
    scoreMax: 100,
    infoTerm: "screen-bolton",
    resultsTitle: "S&P 500, ranked as contrarian candidates",
    resultsBlurb:
      "Cheap, out of favour, and solvent enough to wait. These are not buys: Bolton's own rule is that cheap without a catalyst is a value trap, and the catalyst is the one part of his framework no data feed carries. Open a name and ask him.",
    label: "Bolton Contrarian",
    description:
      "Anthony Bolton's special-situations framework, automated as far as it honestly can be: valuation, neglect, balance-sheet strength and stabilisation. The catalyst section is deliberately not scored — that judgment belongs to the Bolton persona on a company's own page.",
    usesApi: true,
    criteriaSections: [
      {
        title: "Hard filters (all required)",
        items: [
          "Market cap above $300M — below that the spread and disclosure make it academic",
          "Cheap on at least one measure: P/E < 15, P/B < 1.5, EV/EBITDA < 9, or P/FCF < 15",
          "Out of favour: sitting in the lower 60% of its own 52-week range",
          "Positive operating cash flow — it has to fund the wait",
          "Debt/equity below 2.5x, and interest cover above 1.5x where there is debt to service",
        ],
      },
      {
        title: "Score (out of 100)",
        items: [
          "Valuation 30 — the four multiples against his stated thresholds, rescaled by how many are available",
          "Neglect 25 — position in the 52-week range, short interest, analyst coverage, institutional ownership",
          "Balance sheet 20 — debt/equity, interest cover, cash flow versus reported profit",
          "Insider conviction 15 — open-market purchases minus sales over the last year",
          "Stabilisation 10 — down, but no longer falling",
        ],
      },
      {
        title: "Not scored, and why",
        items: [
          "Catalysts — restructurings, spin-offs, hidden assets, legal overhangs lifting, earnings inflections — need reading, not arithmetic",
          "Institutional selling needs 13F history, which this app does not hold; only the current ownership level is used",
          "Every row is therefore a candidate for the question 'what changes this?', never an answer to it",
        ],
      },
    ],
    criteria: [],
    plays: [],
  },
  {
    id: "kiyohara_handbook",
    screenId: "kiyohara-handbook",
    scoreMax: 100,
    infoTerm: "screen-kiyohara",
    resultsTitle: "Japanese mid and small caps, ranked on his own checklist",
    resultsBlurb:
      "TOPIX Mid400 and Small 1, from the Tokyo exchange's own listing file. Every name here is under the loosest of his four P/E ceilings on the second-year forecast and has an equity ratio thick enough not to need a share issue. Which ceiling actually applies is a judgment about the business, and the founder's stake is not in any feed — both are left to the reader, and to the Kiyohara persona on a company's own page.",
    label: "Kiyohara Handbook",
    description:
      "Tatsuro Kiyohara compounded roughly 93x over three decades in Japanese small and mid caps, then retired and published what he looks at: one page of the Japan Company Handbook. This is that page — second-year P/E against the ceiling the business earns, the shareholder register, the equity ratio, net cash against market value, and whether the company has ever asked the market for money. Nothing else, because he says to ignore everything else.",
    usesApi: true,
    criteriaSections: [
      {
        title: "Hard filters (all required)",
        items: [
          "A second-year earnings forecast exists and is positive — his whole method prices next year, so without one there is nothing to judge",
          "Second-year P/E under 20x, the loosest of his four ceilings",
          "Real estate under 10x — the one tier a sector code settles, and the band he worked in",
          "Equity ratio of at least 30%: enough cushion that a downturn does not become a share issue",
          "Market cap above ¥10bn, applied in the currency the company reports in rather than converted at an invented rate",
        ],
      },
      {
        title: "Score (out of 100)",
        items: [
          "Valuation 30 — the second-year P/E itself, scored against 20x rather than against a tier the screen cannot know",
          "Forecast 20 — second-year earnings against the first year, weighted heavier than the first year against trailing, because the price already reflects next year",
          "Equity ratio 20 — 30% is the floor, 70% is full marks",
          "Net cash 15 — net cash over market cap, how much of the price is handed back to you",
          "Capital structure 10 — share count flat or falling; a buyback scores, a financing issue scores nothing",
          "Closely held 5 — insiders' aggregate stake, the most the data can say about the register",
        ],
      },
      {
        title: "His four P/E ceilings — reported, not chosen",
        items: [
          "Under 20x: high market share in a global niche",
          "Under 15x: lower share, but many credible customers",
          "Under 10x: small or mid-cap real estate — his bread and butter",
          "Under 7x: a subcontractor or tier-two supplier with concentrated customers",
        ],
      },
      {
        title: "Not scored, and why",
        items: [
          "Which ceiling applies — market share, niche, customer concentration — needs reading, not a sector code. Every row records that the business type was never checked",
          "The founder and family stake, which is what the inheritance-tax trade turns on: the Handbook names them, the feed gives one anonymous insider percentage",
          "Dividend, price chart, broker ratings and momentum are absent by his instruction, not by omission",
          "Forecasts are the analyst consensus for next fiscal year, a substitute for the Handbook's own Toyo Keizai estimate rather than the same number",
        ],
      },
    ],
    criteria: [],
    plays: [],
  },
];

export const DEFAULT_SCREENER_ID = SCREENER_VIEWS[0]!.id;

export function getScreenerById(
  id: string | undefined,
): ScreenerViewDef | undefined {
  if (!id) return undefined;
  return SCREENER_VIEWS.find((v) => v.id === id);
}
