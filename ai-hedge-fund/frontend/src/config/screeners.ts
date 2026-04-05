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
};

export const SCREENER_VIEWS: ScreenerViewDef[] = [
  {
    id: "breakout",
    label: "Breakouts",
    description: "Momentum and range-break candidates with defined risk.",
    criteria: [
      "52-week proximity or fresh highs",
      "Volume confirmation vs 20d average",
      "Trend alignment (e.g. price > 50d MA)",
    ],
    plays: [
      {
        ticker: "—",
        setup: "Add your first watch via data or manual rows",
        entry: "—",
        stop: "—",
        target: "—",
        sizePct: undefined,
        sizeNotes: "Risk per trade / max position %",
        notes: "Replace this placeholder when you wire criteria.",
      },
    ],
  },
  {
    id: "pullback",
    label: "Pullbacks",
    description: "Trend-following entries on controlled dips.",
    criteria: [
      "Uptrend intact on higher timeframe",
      "Pullback to support or moving average",
      "No broken structure / lower lows on the swing",
    ],
    plays: [],
  },
  {
    id: "catalyst",
    label: "Catalysts",
    description: "Event-driven setups (earnings, FDA, product, M&A).",
    criteria: [
      "Dated catalyst within your horizon",
      "Liquidity and spread acceptable for size",
      "Scenario table: bull / base / bear",
    ],
    plays: [],
  },
  {
    id: "yartseva",
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
];

export const DEFAULT_SCREENER_ID = SCREENER_VIEWS[0]!.id;

export function getScreenerById(id: string | undefined): ScreenerViewDef | undefined {
  if (!id) return undefined;
  return SCREENER_VIEWS.find((v) => v.id === id);
}
