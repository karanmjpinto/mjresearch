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

/**
 * The backend screen names, written once.
 *
 * This union was spelled out by hand in three files — here, in
 * `ScreenResults`'s props, and in its glossary sibling — so adding a screen
 * meant finding all three, and missing one produced a type error two
 * components away from the change that caused it. The list of screens has
 * exactly one home and this is it; everything else imports.
 */
export type ScreenName =
  | "yartseva"
  | "acquisition-compounder"
  | "bolton-contrarian"
  | "kiyohara-handbook"
  | "ellenbogen-two-act"
  | "ai-rollup"
  | "cambrian-scarcity";

/** The glossary term that explains each screen, same reasoning as above. */
export type ScreenInfoTerm =
  | "screen-yartseva"
  | "screen-acquisition"
  | "screen-bolton"
  | "screen-kiyohara"
  | "screen-ellenbogen"
  | "screen-ai-rollup"
  | "screen-cambrian";

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
  screenId?: ScreenName;
  /** Highest attainable score, for the result bars. */
  scoreMax?: number;
  /** Glossary term for the results heading. */
  infoTerm?: ScreenInfoTerm;
  /** Heading and blurb for the pre-computed results panel. */
  resultsTitle?: string;
  resultsBlurb?: string;
  /**
   * Keep the screen out of the picker without removing it.
   *
   * Same mechanism, and same reasoning, as `visible` on the nav destinations:
   * the definition stays in this array, `/screeners/<id>` still resolves, the
   * cached run in `data/screens/` still loads, and the backend screen is
   * untouched. Only the row of tabs gets shorter.
   *
   * Used for exactly one screen today. Bolton's framework ranks companies by
   * how out of favour they are — cheap on a multiple, sitting in the lower
   * 60% of their own 52-week range — which is the inverse of what a quality
   * desk is looking for. It is a genuinely useful counterweight when the
   * question is "am I paying up for comfort", and a confusing thing to sit
   * next to a quality screen as an equal.
   */
  hidden?: boolean;
};

export const SCREENER_VIEWS: ScreenerViewDef[] = [
  {
    /* Not a screen of ours: the curated buy-side's week, then the Bolton
     * screen over the same names. Visible even though Bolton is hidden,
     * because here it answers a narrower question — which of the names other
     * people are excited about also clear the cheap-unloved-solvent test. */
    id: "buyside_ideas",
    label: "Buy-side ideas",
    description:
      "Names the curated buy-side wrote about in the last week, from Bullpen.News's hand-picked newsletters, fund letters and X accounts — written-up catalysts first — and the Bolton screen run over the same list. The list is other people's opinion; the table is our arithmetic.",
    criteriaSections: [
      {
        title: "Where the list comes from",
        items: [
          "The Bullpen.News RSS feed, about six days deep, read at most every six hours",
          "Catalyst means Bullpen tagged the item special situation, M&A or activism — someone wrote it up, not that it is real",
          "New means the name is outside the S&P 500, 400 and 600, so no screen here has seen it",
        ],
      },
      {
        title: "What the table under it is",
        items: [
          "The Bolton contrarian screen, unchanged, over the 'Buy-side this week' universe",
          "Leads are attached to passing rows only and never change a score",
        ],
      },
    ],
    criteria: [],
    plays: [],
  },
  {
    id: "cambrian_scarcity",
    screenId: "cambrian-scarcity",
    scoreMax: 100,
    infoTerm: "screen-cambrian",
    label: "AI Supply-Chain Scarcity",
    resultsTitle: "The scarce physical inputs, ranked",
    resultsBlurb:
      "Cambrian's thesis as a list: wafer, memory, capacitor and foundry makers that own their factories, scored on how cheap they are on forward revenue, how much operating leverage sits in the plant, how far margins are below their own best year, whether demand is arriving, and whether the balance sheet survives the cycle coming back. Fabless and software names are in the universe so the chart can compare them; they cannot pass. Whether a company's buyers are price-inelastic — the trait Cambrian calls key — is listed as unchecked on every row.",
    description:
      "After Cambrian Capital's September 2026 thesis: as compute gets more valuable, value flows to the scarce physical inputs that make it, and many of those still trade at 1–5x revenue while software trades at 13–100x. Hard filters on segment and on owning factories (net plant at least 0.2x revenue, which is what separates a fab from a fabless designer). Then 100 points: revenue multiple 35, operating leverage 20, idle capacity 15, demand arriving 15, balance sheet 15. Read with the thesis panel above, which carries Cambrian's own segment estimates.",
    usesApi: true,
    criteria: [
      "Segment: wafers, memory, capacitors or foundries, from a curated list. Off the list, the industry label must be semiconductors, semiconductor materials or electronic components",
      "Owns factories: net plant at least 0.2x annual revenue. Makers run 0.37–0.82, the fabless designers 0.04–0.12. Sandisk is exempt by name: its fabs sit in the Kioxia joint venture, off its balance sheet",
      "Revenue multiple: market cap over next-twelve-month consensus revenue, calendarised from two fiscal years. Converted at a quoted FX rate when the listing quotes and reports in different currencies — the provider's own ratio is 8x too high for Hong Kong-listed foundries",
      "Revenue multiple, 35 points: full marks at 2x, none at 8x",
      "Operating leverage, 20 points: contribution over operating profit, with depreciation and operating expense treated as fixed. Cambrian's own example gives 4.7, which is +47% profit on +10% volume. A loss-maker scores the midpoint, not the maximum",
      "Idle capacity, 15 points: how far the operating margin is below its best year in the provider's four or five years of history",
      "Demand arriving, 15 points: forward revenue over trailing",
      "Survives a cycle, 15 points: net debt over EBITDA, full marks at net cash, none at 3x",
      "Memory rows carry a flag: spot-priced memory is a price-taker, which this desk's own principles exclude. Cambrian's answer is that inelastic buyers now set the price — a judgment, so it is flagged and not resolved",
      "NOT scored: whether customers are price-inelastic, real line utilisation, whether supply really cannot scale, the AI timeline itself, and how much of a conglomerate's revenue is the segment",
    ],
    plays: [],
  },
  {
    id: "ai_rollup",
    screenId: "ai-rollup",
    scoreMax: 50,
    infoTerm: "screen-ai-rollup",
    label: "AI Rollup Targets",
    resultsTitle: "Who the AI buyers are shopping for",
    resultsBlurb:
      "Two buyers want opposite things, so there are two scores and no average. A lab buys delivery capacity — OpenAI's DeployCo acquired an AI consultancy for roughly 150 engineers — and wants revenue per head high and technical. An AI-enabled roll-up buys cash-generating operators to compress the labour cost, and wants revenue per head low, because that is where the compressible cost is. The bar is the roll-up score out of 50; the lab score sits beside it and frequently disagrees. What neither score can tell you is whether AI actually compresses this particular business — that is listed as unchecked on every row.",
    description:
      "Who gets bought, by the two buyers who are actually buying. Hard filters on industry, a deliberately low size ceiling (above roughly $8bn you are describing an acquirer, not a target), asset intensity and existing leverage. Then two separate scores out of 50 — roll-up fit and lab fit — built from revenue per employee, the wedge between gross and operating margin, cash conversion, balance sheet, insider holding, and industry fragmentation counted over the universe being screened. The a16z two-paths argument rides along as a warning rather than a score: software that is neither growing 10 points faster nor rebuilt for 40% operating margins is flagged as the comfortable middle, which is a reason not to own it rather than a reason to buy it.",
    usesApi: true,
    criteria: [
      "Industry: matched against a services allowlist on the label a provider reports. Coarse by admission — a software company whose revenue is two-thirds implementation reads as software here",
      "Size: roughly $50m to $8bn equivalent, in the currency the company is quoted in. The ceiling is the opinionated number — a roll-up buyer wants an operator small enough that the post-automation delta is large and the cheque is writable",
      "Asset intensity: capex below 12% of revenue, so the price is for cash flows rather than for plant",
      "Leverage: net debt below 4x EBITDA, because a roll-up is serviced out of the target's own cash",
      "Headcount must be reported. Without it there is no labour intensity, and labour intensity is the whole screen — refused rather than scored as zero, which would read as a business with no staff",
      "Roll-up score: labour intensity 10, margin wedge 10, fragmentation 8, cash conversion 8, balance sheet 8, owner-operator 6",
      "Lab score: revenue per head read the other way up, a bonus for IT services and consulting shells, and growth",
      "NOT scored: whether the work is documented well enough for a model to learn it, how much of the delivery is judgment a customer is paying a person for, whether customers accept being served by a machine, whether the people who know how it works stay, and whether the seller will sell at all",
    ],
    plays: [],
  },
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
    scoreMax: 50,
    infoTerm: "screen-acquisition",
    resultsTitle: "Quality compounders, ranked on the ten-factor score",
    resultsBlurb:
      "The quality screen on this desk. Every name here cleared the hard filters — a return on capital above 12%, cash conversion above 80%, and a share count that is flat or falling — and sits inside the small and mid-cap band. The bar is its ten-factor score out of 50. The tenth factor is the reinvestment runway: not what the capital already deployed earns, but what the business can compound at from its own cash. Pick a universe to run it somewhere else.",
    label: "Quality Compounder",
    description:
      "The compounder test, in Akre's three legs: an extraordinary business, management who do not dilute you, and somewhere to put the next dollar at the same rate. Hard filters on growth, ROIC, FCF conversion, leverage, margin trend and dilution, then a ten-factor score out of 50. Bounded to small and mid caps and runnable on any of the eighteen universes. Data via yfinance; short histories fall back to span CAGR — verify in filings.",
    usesApi: true,
    criteria: [
      "Size: roughly $500m to $20bn, applied in the currency the company reports in rather than converted at an invented rate. A company whose currency has no band is refused rather than waved through",
      "Hard filters: revenue & EPS/FCF-per-share growth, revenue YoY proxy >3%, ROIC >12%, FCF/NI >80%, margin trends, net debt/EBITDA <3x, interest coverage >4x, share CAGR <2%, goodwill impairment heuristic",
      "Tier 2 (optional): stricter growth/ROIC/FCF margin/FCF-ps vs revenue / leverage",
      "Reinvestment runway: the reinvestment rate (capex plus acquisitions over operating cash flow) multiplied by the return on *incremental* capital. Their product is what the business can compound at unaided. Scored 1-5 between 3% and 18%",
      "Score tiers: 39+ strong, 44+ elite (weak below 31), rescaled in proportion when the tenth factor was added",
      "Not scored: how the acquisitions are actually done, and whether management is any good. Both need reading. The committee on a company's own page is where that goes",
      "ROIIC is left unmeasured, and the factor scored neutral, when the capital base barely moved or shrank — the ratio would be noise. A capital-light business that grows profit without adding capital is not penalised for it",
    ],
    plays: [],
  },
  {
    id: "bolton_contrarian",
    screenId: "bolton-contrarian",
    hidden: true,
    scoreMax: 100,
    infoTerm: "screen-bolton",
    resultsTitle: "S&P 500, ranked as contrarian candidates",
    resultsBlurb:
      "Cheap, out of favour, and solvent enough to wait. These are not buys: Bolton's own rule is that cheap without a catalyst is a value trap, and the catalyst is the one part of his framework no data feed carries. Where the curated buy-side has written one up, the row says so. Open a name and ask him.",
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
          "Passing rows show catalysts the buy-side has written up on Bullpen.News (special situation, M&A, activism, last six months) as leads. They are not scored and do not mark the catalyst as checked",
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
  {
    id: "ellenbogen_two_act",
    screenId: "ellenbogen-two-act",
    scoreMax: 100,
    infoTerm: "screen-ellenbogen",
    resultsTitle: "S&P SmallCap 600, ranked on the compounder signature",
    resultsBlurb:
      "The shelf Ellenbogen's own study points at: about 80% of the companies that compound at 20% a year for a decade begin that run as small caps. Every name here is growing, earns money at the size it already is, and makes a rising return on the capital it employs. The bar is its score out of 100. What the screen has not done is find the second act — and by his framework that is the entire question, so a passing row is a candidate for it rather than an answer to it.",
    label: "Ellenbogen Two-Act",
    description:
      "Henry Ellenbogen ran T. Rowe Price New Horizons at 19.2% a year, with over 90% of the alpha coming from 20 compounders held longer than four years. His framework asks whether a company can make the leap from Act 1 — proven product-market fit and unit economics — to Act 2, something fundamentally larger. The financial signature of Act 1 is scored here out of 100, led by the trait his research actually found: returns on invested capital that rise as the business gets bigger. The second act is left where it belongs, with the reader and with his persona on a company's own page.",
    usesApi: true,
    criteriaSections: [
      {
        title: "Hard filters (all required)",
        items: [
          "Size roughly $1bn to $20bn, in the currency the company reports in. The floor is his study's own starting band for a small-cap compounder; a currency with no band is refused rather than converted at an invented rate",
          "Revenue CAGR above 12% — not the 20% that defines a compounder, but on that path",
          "Revenue still growing above 8% year on year. A flattering five-year CAGR on a business that has stopped is the main way this screen could mislead",
          "A profitable core: operating margin above zero. This is the imposter filter — 'that's not the Amazon story', whose retail business held 5–7% margins before it funded anything else",
          "Return on invested capital above 10%, deliberately below the compounder screen's 12%, because here the slope matters more than the level",
          "Gross margin above 20% where the provider reports one; a missing gross-profit line is not a failure",
          "Share count growing no faster than 4% a year",
        ],
      },
      {
        title: "Score (out of 100)",
        items: [
          "Returns on invested capital 30 — 18 for the level, 12 for the slope. The slope is the signature trait his research found: businesses that got better as they got bigger",
          "Act 1 evidence 25 — revenue CAGR against his 20% bar, growth now, and an operating margin that proves the unit economics at the scale already reached",
          "Reinvestment runway 20 — the reinvestment rate multiplied by the return on incremental capital, which is what the business can compound at from its own cash",
          "Owner alignment 15 — a share count that is flat or falling, and insiders with something to lose",
          "Pricing power 10 — gross margin level, and whether it has held or widened as the business grew",
        ],
      },
      {
        title: "The slope, and when it is not measured",
        items: [
          "'Better as it got bigger' needs the bigger. When revenue grew less than 20% across the window the slope scores neutral and the row says why — margin recovery on a flat business is a different and far commoner story",
          "A buyback retires equity, and equity sits inside invested capital, so a company shrinking its capital base shows a rising return with no operating improvement at all. A capital base down more than 5% also scores neutral",
          "Neutral means 6 of 12, not zero. The row carries the reason, so a middling slope score is never confused with a measured mediocre one",
          "And the return itself is reported as unrankable, scored neutral, when the capital base has been bought back to almost nothing — one real small cap prints a 530% return on this definition purely because years of buybacks left the denominator near zero",
        ],
      },
      {
        title: "Reported, deliberately not scored",
        items: [
          "The drawdown from the five-year high. His study found that in the ten years a compounder grew at 20%, one of those years it fell about 62% — usually during the transition, not in a crash",
          "A name that clears every filter and is down past 40% is flagged a transition candidate. That marks where the question gets asked, not an answer: scoring it would turn this into a falling-knife screen",
          "How short of his window the measurement is. His compounder is a ten-year fact and the provider returns four or five annual columns for a small cap, so the growth rate here is usually a three- or four-year CAGR. Every row says how many years it had",
        ],
      },
      {
        title: "Not scored, and why",
        items: [
          "The second act itself — a new product, a new market, becoming something larger. It is a judgment about a thing that does not exist yet, and every row records that it was never checked",
          "Whether this is an Act 2 operator: he preferentially backs founders who have already built a business at scale, and no feed carries who the insiders are, let alone what they built before",
          "Failing or transitioning. By his own account that distinction is the job, and it needs a person",
          "One house override: his own book held software names that funded themselves with stock. This desk will not, so the dilution ceiling here is real and some of his actual positions would fail it",
        ],
      },
    ],
    criteria: [],
    plays: [],
  },
];

/**
 * Where `/screeners` lands, and therefore which screen leads the tab row.
 *
 * Named rather than taken from `SCREENER_VIEWS[0]`, because array position is
 * not an argument. This desk looks for quality, the compounder test is the
 * screen that measures quality, so it is the one you land on. The multi-bagger
 * screen stays — it is a different and useful question — but it ranks 55% on
 * valuation and 15% on returns, so it is a cheapness screen, and leading with
 * it would misdescribe the desk.
 */
export const DEFAULT_SCREENER_ID = "acquisition_compounder";

/**
 * The screens the picker lists, default first. A hidden one is absent from
 * this list and still reachable at `/screeners/<id>`.
 *
 * Ordered off `DEFAULT_SCREENER_ID` rather than carried as a second list of
 * ids, so there is one place that decides what leads and no way for the tab
 * row and the redirect to disagree.
 */
export const VISIBLE_SCREENER_VIEWS = SCREENER_VIEWS.filter((v) => !v.hidden).sort(
  (a, b) =>
    Number(b.id === DEFAULT_SCREENER_ID) - Number(a.id === DEFAULT_SCREENER_ID),
);

/**
 * Resolves against every screen, including hidden ones, so a saved link or a
 * bookmark to a hidden screen still opens it rather than redirecting away.
 */
export function getScreenerById(
  id: string | undefined,
): ScreenerViewDef | undefined {
  if (!id) return undefined;
  return SCREENER_VIEWS.find((v) => v.id === id);
}
