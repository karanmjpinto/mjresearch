/**
 * The reference section: what this app computes, what it writes, and which is
 * which.
 *
 * Kept as data rather than JSX so the page cannot drift into prose that no
 * longer matches the build. Two rules for editing it:
 *
 *   1. Every capability carries a `trust` label. That label is the point of
 *      the whole document — a reader deciding whether to act on a number needs
 *      to know whether it was calculated or predicted, and nothing else on the
 *      page answers that.
 *   2. `gaps` is not a disclaimer section. It lists the specific things that
 *      are known to be missing or wrong, because a reference that only
 *      describes what works teaches the reader to trust the parts that don't.
 *
 * When a feature lands, add it here in the same change. A feature the docs do
 * not mention is a feature nobody else can evaluate.
 */

/**
 * How much a given output can be relied on to be the same tomorrow, and where
 * it came from.
 *
 * The distinction that matters is not "AI or not" — it is whether a figure was
 * *calculated* or *predicted*. A predicted figure can be correct, plausible
 * and wrong in the same breath; a calculated one can be re-derived and argued
 * with. Most of this app is deliberately the second kind.
 */
export type Trust = "computed" | "chosen-then-computed" | "written" | "judged";

export const TRUST_META: Record<
  Trust,
  { label: string; hue: string; meaning: string }
> = {
  computed: {
    label: "Computed",
    hue: "var(--verdigris-paper)",
    meaning:
      "Plain Python over a frozen snapshot. Same inputs give the same answer, every time, and you can read the function that produced it.",
  },
  "chosen-then-computed": {
    label: "Model chooses, code computes",
    hue: "var(--cobalt-paper)",
    meaning:
      "A model decides which measurements to take, from a fixed catalogue, and never sees a value. The measurements themselves are Python. The choice can vary between runs; the arithmetic cannot.",
  },
  written: {
    label: "Model-written",
    hue: "var(--cadmium-paper)",
    meaning:
      "Prose generated over figures the model did not produce. Expect the wording to change between runs. Any number appearing here is checked against the snapshot afterwards.",
  },
  judged: {
    label: "Model judgment",
    hue: "var(--oxide-paper)",
    meaning:
      "An opinion — a stance, a conviction score, a hypothesis. Not reproducible, not a calculation, and the part of the app to trust least and argue with most.",
  },
};

export type DocSection = {
  id: string;
  title: string;
  /** One line that answers "why does this section exist". */
  standfirst: string;
  body: string[];
  items?: { name: string; trust: Trust; detail: string }[];
};

export const OPENING = {
  oneLine:
    "A single-investor equity research and portfolio workstation that runs on your own machine.",
  thesis:
    "The organising rule is that a language model is never the source of a number. A question is compiled into a typed plan of registered Python metrics; the planner chooses what to measure and is not shown any values; Python computes them; and only then does a model write prose over results it did not produce. Everything else in this document follows from that one decision.",
};

export const SECTIONS: DocSection[] = [
  {
    id: "determinism",
    title: "What is calculated, and what is predicted",
    standfirst:
      "The single most useful thing to know before acting on anything this app says.",
    body: [
      "Every capability below is labelled with where its output comes from. The labels are not a formality: a screen score and a persona's conviction score both render as a number between 0 and 100, and they are entirely different kinds of claim. One is arithmetic you can re-run. The other is an opinion that will come out differently tomorrow.",
      "Where the two meet, the calculation wins by construction. When the plan pipeline computes a conviction score, it overwrites whatever the model wrote and records both values — the run keeps `model_said` alongside `harness_used`, so a disagreement is visible rather than silently resolved.",
    ],
    items: [
      {
        name: "Valuation — reverse DCF, implied expectations, comps",
        trust: "computed",
        detail:
          "Solved by bisection over the pricing function rather than a derivative method, because value clamps, jumps at the terminal year, and is not monotonic everywhere. When no growth rate reproduces the market price the answer is 'no solution', never the nearest edge of the bracket.",
      },
      {
        name: "Portfolio construction — weights and risk",
        trust: "computed",
        detail:
          "Equal weight, inverse volatility, mean-variance, hierarchical risk parity, and conviction weighting. Returns are aligned on common trading days; Sharpe, volatility, drawdown and effective N are computed from those aligned series.",
      },
      {
        name: "The three screens",
        trust: "computed",
        detail:
          "Every filter and every score is arithmetic over fetched fundamentals. No model reads a screen or ranks it. Results are computed ahead of time and served from a dated cache, so what you see is a list, not a request.",
      },
      {
        name: "Factors — JKP theme returns and where a company sits on them",
        trust: "computed",
        detail:
          "The theme and factor returns are Jensen, Kelly and Pedersen's published US series from jkpfactors.com, stored as a dated file; the Sharpe ratios and the in-sample/after-sample split are plain arithmetic over them. The company's tilt is a percentile rank against the cached screen universes. No model reads or writes any of it.",
      },
      {
        name: "Regimes — clustering whole return distributions",
        trust: "computed",
        detail:
          "Each quarter of returns is treated as a distribution and clustered in Wasserstein distance (Horvath, Issa and Muguruza, SSRN 3947905), rather than being reduced to a volatility number and thresholded. No model is involved and the same inputs always give the same labels. The tab also scores its own split, and scores the volatility rule it replaces on the same windows, so the reader can see whether the regimes are real.",
      },
      {
        name: "Constraint flow — where the investable surface is",
        trust: "computed",
        detail:
          "A Sankey over the curated constraint map whose width is the count of listed companies named against each chokepoint. Nothing in the map carries a dollar figure, so the flow is denominated in companies and the caption says so; each system is ordered by how far past normal its worst-measured leg sits. No model touches it, and a chokepoint with no `normal` to measure against is still drawn, just not ranked.",
      },
      {
        name: "Macro map — growth and inflation sensitivities",
        trust: "computed",
        detail:
          "Two quarterly news metrics built from FRED (CPI, real GDP) and the Philadelphia Fed's Survey of Professional Forecasters, stored as a dated file; a point is the partial correlation of a series' twelve-month returns to one metric holding the other fixed. The reference series are Kenneth French's market and industry portfolios and the same JKP themes as the Factors tab; only the company's own point is fetched live. No model touches any of it, and every point carries the standard error its overlapping windows imply.",
      },
      {
        name: "Backtests and the out-of-sample test",
        trust: "computed",
        detail:
          "Rule evaluation, the walk-forward split, and the significance bar that rises as more variants are tried are all deterministic. Only the proposal of a rule involves a model.",
      },
      {
        name: "Sizing against the book you already hold",
        trust: "computed",
        detail:
          "Resulting weight, correlation to existing holdings, concentration, and the effect on total portfolio volatility. A volatile name can reduce total risk if it moves differently from what you own, and this is where that shows up.",
      },
      {
        name: "Claim verification",
        trust: "computed",
        detail:
          "A pass re-reads the finished thesis, extracts each numeric claim, and compares it against the snapshot and the computed facts. Claims it cannot map are reported as unverifiable — never as passing.",
      },
      {
        name: "Which metrics to compute",
        trust: "chosen-then-computed",
        detail:
          "The planner picks from a fixed catalogue of registered metrics and emits a typed plan. It sees names, not numbers. An edited plan can be replayed without re-planning, which is how you hold the choice fixed and vary nothing else.",
      },
      {
        name: "The investment thesis, risks and narration",
        trust: "written",
        detail:
          "Written over computed results. The wording varies between runs even with greedy, seeded sampling, because no provider guarantees identical output. Numbers inside it are verified afterwards.",
      },
      {
        name: "Investor opinions and the committee verdict",
        trust: "judged",
        detail:
          "Each investor returns a stance and a conviction score in their own style; a synthesis step reconciles the disagreement. These run with full freedom rather than as weightings over computed dimensions, so unlike the plan pipeline they are not reproducible. Treat the spread between investors as the useful signal, not the headline number.",
      },
      {
        name: "Trading-rule hypotheses",
        trust: "judged",
        detail:
          "The autoresearch proposer invents rules to test. What it invents is not reproducible; what happens to the rule afterwards is entirely deterministic.",
      },
    ],
  },
  {
    id: "pipeline",
    title: "How a question becomes an answer",
    standfirst:
      "The model appears twice, in two narrow roles, and is the source of no figure in between.",
    body: [
      "Market data is fetched once and frozen, so every stage downstream reads the same content-addressed snapshot. The planner turns the question into a typed plan. The executor computes every figure in Python. A narrator writes prose over those results. The harness then validates the output, verifies each numeric claim, and overrides the conviction score with the computed one where a plan produced it. The run is persisted whole — snapshot, prompts, model parameters, output — so two runs can be compared rather than argued about.",
      "The order matters more than the parts. Handing a model a pile of data and asking for a verdict makes every figure in the answer a token prediction. Splitting the choice of measurement from the measurement itself means a wrong answer can be traced to either a bad plan or bad data, and fixed at the method level instead of being corrected number by number.",
    ],
  },
  {
    id: "screens",
    title: "The three screens",
    standfirst:
      "Each one is a different question, pointed at the universe it was designed for.",
    items: [
      {
        name: "Yartseva multibagger — S&P SmallCap 600",
        trust: "computed",
        detail:
          "Hard filters on size, profitability, balance sheet and sector, then a weighted composite out of 100 (free-cash-flow yield, book-to-market, return on assets, investment quality, size, entry timing). It runs on the small-cap index by necessity: the screen caps market value at $2bn, so it cannot pass a single S&P 500 name.",
      },
      {
        name: "Acquisition compounder — S&P 500",
        trust: "computed",
        detail:
          "Growth, return on invested capital, cash conversion, leverage, margin trend and dilution as hard filters, then a nine-factor score out of 45. Organic growth is a revenue proxy, not a reported figure, so a company growing purely by acquisition can read as organic — check the segment disclosures.",
      },
      {
        name: "Bolton contrarian — S&P 500",
        trust: "computed",
        detail:
          "Anthony Bolton's special-situations framework, automated as far as it honestly goes: cheap on at least one multiple, sitting low in its own 52-week range, and generating enough cash to survive the wait. Scored out of 100 across valuation, neglect, balance sheet, insider buying and whether the fall has stopped.",
      },
    ],
    body: [
      "The Bolton screen is deliberately incomplete, and the gap is the most important thing about it. His framework has five sections and only four can be computed. The fifth is the catalyst — a restructuring, a hidden asset, a legal overhang lifting, an earnings inflection still priced as decline — and that is the section he says separates a re-rating from a value trap. It cannot be read from a data feed.",
      "So the screen does not score it and does not pretend to. Every row it returns records that the catalyst was never checked, and by Bolton's own reasoning a name that passes is a value trap until someone finds one. That judgment is the Bolton persona's job on a company's own page, which is why the screen's output links there instead of ending in a verdict.",
    ],
  },
  {
    id: "investors",
    title: "The investor committee",
    standfirst:
      "Fifteen investors are available; seven speak by default, chosen to disagree for different reasons.",
    body: [
      "Each investor is a prompt built from a stored profile: who they are, how they think, and the concrete tests they apply. The app shows you those tests next to their verdict, and both come from the same source — a description kept separately from the instruction would eventually tell you an investor weighs one thing while the model had been told to weigh another.",
      "The default committee is Buffett, Graham, Wood, Burry, Bolton, Druckenmiller and Damodaran. Each covers an axis the others do not: business quality, statistical cheapness, disruption, the bear case, the unloved-with-a-catalyst, the macro regime, and whether the price's own assumptions are internally consistent. A committee of near-duplicates produces a confident consensus that reflects one way of looking, which is worse than a narrower claim honestly made.",
      "Read the spread, not the average. Seven investors agreeing tells you less than two of them disagreeing for a reason you had not considered.",
    ],
  },
  {
    id: "lookback",
    title: "Portfolio construction looks backwards",
    standfirst: "Every figure on that screen is measured, not forecast.",
    body: [
      "Weights, expected returns, volatilities and the correlations the weights are derived from are all computed over one historical window, and nothing outside it. The screen draws that window as a dated bar with an arrow pointing into the past, because a table of two dates makes the reader do the subtraction and a backtest read as a forecast is the most expensive misreading available here.",
      "Two years of history and ten are different claims. Where the requested window is longer than the shortest price history in the basket, the window silently shortens for everything — so the shortfall is stated rather than left to be noticed.",
    ],
  },
  {
    id: "factors",
    title: "Factors, and whether they survived being published",
    standfirst:
      "A century of factor returns from the replication-crisis paper, and one company placed on them.",
    body: [
      "The Factors tab under Analysis draws the thirteen themes of the Jensen–Kelly–Pedersen dataset — value, momentum, quality, profitability, investment, low risk, low leverage, size, accruals, debt issuance, profit growth, short-term reversal and seasonality — from their US, monthly, capped value-weighted long-short portfolios back to 1926. The returns are theirs, reshaped by scripts/refresh_jkp.py into a committed file that records the last month it covers, so the tab works offline and never silently changes between two page loads.",
      "Pick a theme and every factor inside it is split around the years its original paper studied: a Sharpe ratio inside that sample, and one after it ended. That is the paper's own question — does a published anomaly keep working once it is known — asked factor by factor. Most shrink; the bar is whether the return stayed positive, not whether it stayed the same size.",
      "The company's tilt is this app's own measurement, not JKP's. Each characteristic it can compute from the fetched fundamentals is ranked against the roughly eleven hundred names in the cached screens, flipped where JKP buy the low end so that above 50 always means the side the factor buys, and averaged into its theme. Approximations are marked where they differ from JKP's definition, and a theme with nothing measurable is left blank rather than shown as a neutral 50.",
    ],
  },
  {
    id: "regimes",
    title: "Regimes, and how to tell whether one is real",
    standfirst:
      "Clustering whole return distributions instead of thresholding a volatility ratio — and a score that says whether the division holds.",
    body: [
      "The Regimes tab under Analysis cuts a company's price history into overlapping windows of about a quarter, treats each window as a distribution of daily returns rather than as a set of summary statistics, and clusters those distributions in 1-Wasserstein distance. The method is Horvath, Issa and Muguruza (SSRN 3947905). In one dimension the optimal transport problem has a closed form — sort two windows and average the absolute differences — so this is ordinary numpy and needs no solver, and a regime's centre is the pointwise median of its members, which is why a single crash window cannot drag it.",
      "It replaces a rule that compared recent volatility to a longer baseline and cut the ratio at 1.25. That rule used one moment and two thresholds nobody derived. On synthetic paths where the regime changes are planted and therefore known, clustering distributions catches substantially more of them than the ratio does, and the gap widens when returns jump — which is the case real equity returns resemble. Those paths are in tests/test_regimes.py as an accuracy floor, because real market data has no answer key and any accuracy figure quoted on it is either circular or someone pointing at a chart.",
      "The first thing on the tab is not the regimes but the separation ratio, because any clustering returns clusters: ask k-means for two groups and it produces two, whether or not two exist, and the resulting chart is equally convincing either way. The ratio measures how much more a window resembles its own group than the other, using a maximum mean discrepancy two-sample statistic. Above 1 the split means something; at or below 1 it is one population cut in half. The same score is computed for the volatility rule on identical windows with an identical kernel, and shown beside it — including on the names where the old rule wins.",
      "Two limits are structural rather than temporary. The clustering is fitted over the whole period at once, so every label was assigned knowing what came after it: this describes where a company has been and must not be backtested on or treated as a signal. And it labels rather than predicts — which regime you are in now says nothing here about which comes next.",
    ],
  },
  {
    id: "macro",
    title: "The macro map, and what a wide error bar means",
    standfirst:
      "Which growth and inflation surprises a series has been paid for, over fifty years — and why the quadrant is the reading, not the decimal.",
    body: [
      "The Macro map tab under Analysis places return series on two axes: sensitivity to US inflation news and to US growth news. The method is AQR's, from Alternative Thinking 2026 Issue 3, which in turn follows Brixton, Maloney and Thapar (2021). Prices already contain the inflation everyone expects, so the axes measure news rather than level, and each news metric blends two imperfect readings of it — how far the year-on-year rate moved from the year before, and how far it landed from the forecast made a year earlier. Each leg is divided by its own standard deviation before averaging, so the blend is not quietly dominated by whichever is more volatile.",
      "A point is a partial correlation: its inflation sensitivity is measured holding growth news fixed, and the reverse. Simple correlations would not do, because the two metrics are not independent and a series that only ever responded to growth would pick up an inflation reading through the overlap. The four quadrant names describe the environment, not the asset — a series in the stagflation quadrant is one whose good years have been the ones with rising inflation and falling growth.",
      "The macro series come from FRED and the Philadelphia Fed's Survey of Professional Forecasters, the market and industry returns from Kenneth French's library, and the factor themes from the same JKP file the Factors tab reads; scripts/refresh_macro_news.py writes them into one dated file, so the map draws offline. The company's own point is the only thing fetched live, and a company without about eleven years of monthly prices is told it is too short rather than given a point.",
      "The honest part is the ring. These are twelve-month returns read off every quarter, so consecutive readings share nine months of the same data: half a century of quarters carries roughly fifty independent observations, and a correlation on fifty observations has a standard error near 0.14. Two points a tenth apart have not been shown to differ. The ring is drawn at that width on whatever is being read, and the Years column says how much history is actually behind each row.",
    ],
  },
  {
    id: "autoresearch",
    title: "Autoresearch, and why almost everything is discarded",
    standfirst:
      "The searcher only ever sees the in-sample window. The out-of-sample window decides.",
    body: [
      "One strategy is proposed at a time, fitted on one window, and judged on a window it never saw. The bar rises as more variants are tried, because searching enough rules against a single price history will always turn something up. Discarded runs stay on the log, since a leaderboard of survivors is how a search process starts looking skilful.",
      "The chart on that page draws one line per experiment, from where it was fitted to where it was tested. Almost every line runs the wrong way. That is the finding, and it is the reason to distrust any backtest — including the ones here — that is presented without its out-of-sample leg.",
    ],
  },
  {
    id: "data",
    title: "Data, provenance and what runs where",
    standfirst: "Several providers, which disagree with each other.",
    body: [
      "Market data comes from keyless providers by default, with fallback and caching, and every fetch records who answered, whether it came from cache, and how the payload verified — frequency, coverage, units. Providers disagree on split adjustment, fiscal alignment and currency, so knowing which source answered is part of reading the number.",
      "The model runs locally through Ollama; the portfolio lives in a SQLite file you own; no API keys are required. Optional keys add coverage. A stage can be pointed at its own model, so bulk work and the hardest judgment step need not use the same one.",
      "Screens are pre-computed and dated. They read quarterly fundamentals, so a run is wrong the moment a company reports — the age is shown next to every list, and past a week it says so in colour.",
      "A refresh now probes the data provider before it starts, and reports one of three states: ok, degraded, or offline. Offline means the provider answered for nothing — so the run does not start and the existing cache is left alone, rather than being overwritten with a complete-looking list that is missing an eighth of its names. That is not hypothetical: it is what happened before the probe existed.",
      "The committee's investor calls run one at a time, not in parallel. The local model server serialises them, so a seven-member run costs roughly seven times one call — about a minute and a half. Measured, not estimated.",
    ],
  },
];

/**
 * The honest list. Ordered by how likely it is to mislead someone, not by how
 * comfortable it is to admit.
 */
export const GAPS: [string, string][] = [
  [
    "This is not investment advice",
    "A research tool. Output is generated by a language model over public data and can be wrong in ways that read perfectly plausibly. Nothing here is a recommendation to buy or sell anything.",
  ],
  [
    "No screen checks a catalyst",
    "The Bolton screen is explicit about it, but it applies to all three: a passing name is a candidate for a question, not an answer to one. Nothing in the app can see a restructuring, a spin-off or a legal overhang lifting.",
  ],
  [
    "Committee conviction is not reproducible",
    "Investor analyses run with full freedom rather than as weightings over computed dimensions. Their conviction scores will move between runs. The plan pipeline's will not.",
  ],
  [
    "The published site does not run the model",
    "Four things here invoke a language model: researching a ticker, the plan pipeline, the backtest, and the autoresearch loop. Those run on your own machine against your own Ollama, which is why they are free and why nothing about your book leaves your computer. The published site deliberately refuses them rather than running them for you on a paid gateway — it can show the screens, the methodology and this reference, and it will tell you plainly when you ask it for analysis it cannot do.",
  ],
  [
    "Only the single-investor path is measured",
    "Twenty cases with pass/fail rules score one investor at a time against frozen company snapshots: whether the answer is well-formed, whether its figures come from the data it was given, and whether the investor's own framework actually applied. The committee — where investors read each other and can revise — is not covered, and it is the path where a prompt change turned the designated bear from a strong sell into a strong buy. Treat a passing score as evidence about one analysis, not about the committee's spread.",
  ],
  [
    "The factor tilt measures less than JKP do",
    "JKP sort on 153 characteristics from CRSP and Compustat. The tilt uses about twenty that the screen caches can supply, some approximated (a six-month return that does not skip the latest month, a five-year sales growth standing in for three), and four themes — low risk, debt issuance, profit growth and seasonality — cannot be measured at all. Peers are the S&P 500 and SmallCap 600 caches, not JKP's full sample, and on the hosted site there are no caches, so there is no tilt. Accounting ratios also mean something different for banks and insurers, which sit in the same ranking.",
  ],
  [
    "Factor returns end where the authors' last update does",
    'The JKP file runs to the month printed on the tab, currently December 2024. "Last 12 months" means the last twelve in that file, not the twelve before today.',
  ],
  [
    "Verification has real gaps",
    "Numeric claims are only checked for metrics the verifier knows about. Anything outside that set counts as unverifiable, not verified, and qualitative claims are not checked at all.",
  ],
  [
    "Regime labels look backwards",
    "The regime clustering is fitted over the whole history at once, so each label used the data around it, including later data. It is descriptive only — it cannot be traded on, and it does not say which regime comes next. Choosing how many regimes to fit is also a setting rather than a finding.",
  ],
  [
    "The macro map is missing the assets that carry the argument",
    "AQR's exhibit plots commodities, gold, inflation-linked bonds, credit and trend-following — the things that sit right of centre and are the point of drawing the map at all. Each needs a licensed index with no free equivalent back to 1972, so none is here, and what remains is an equity map where almost everything crowds into one quadrant. The Treasury line is also a duration approximation from the constant-maturity yield rather than a real total-return index, and the inflation surprise before 1981 uses the GDP deflator forecast because the survey's CPI question does not go back that far.",
  ],
  [
    "The constraint flow counts companies, not money",
    "A reader who has seen a capex Sankey will expect the ribbons to be dollars. They are not: the constraint map holds no money figure anywhere, so a wide ribbon means many listed ways to play a chokepoint and says nothing about the size of the market behind it. The flow also only draws constraints that have at least one name recorded, so a chokepoint nobody has sourced a company for is absent from the picture even though it is in the map.",
  ],
  [
    "Macro sensitivities are half as certain as they look",
    "The map is built on overlapping twelve-month windows read off quarterly, so 218 quarters carry about 54 independent years. Every point's standard error is near 0.14 on a full sample and wider for a company with twenty years of prices. The effective count is a plain divide-by-four rather than a Newey–West correction, which is the cruder of the two honest options.",
  ],
  [
    "Scoring bands are absolute",
    "Valuation scoring uses fixed thresholds rather than sector-relative ones, so a utility and a software company are judged on the same scale.",
  ],
  [
    "Only three universes load",
    "The S&P 500, MidCap 400 and SmallCap 600. The NASDAQ-100, Dow and Russell 2000 loaders all broke upstream when their sources changed shape, and were removed rather than left as options that can only fail. Other markets are available as short curated watchlists, not full indices.",
  ],
  [
    "Institutional selling is not tracked",
    "Current ownership level is available; the change is not, because that needs 13F history this app does not hold. A Bolton-style 'institutions are getting out' signal is therefore missing.",
  ],
  [
    "Prompt order changes the answers",
    "There is a faster prompt arrangement that lets the model reuse work across the seven investors. Measured end to end it saves about a quarter of the run time — and it moved a bear from SELL to BUY on the same company. It is implemented and switched off, because until there is a golden set to judge which ordering is more accurate, the default should be the behaviour that is understood.",
  ],
  [
    "Determinism is bounded",
    "Sampling is greedy and seeded and every input is recorded, but no provider guarantees identical output. Moving the arithmetic out of the model narrows this considerably; it does not eliminate it.",
  ],
  [
    "Data quality is inherited",
    "Fundamentals come from third-party providers that disagree with each other and are sometimes stale. Provenance tells you which source answered. It cannot tell you that source was right.",
  ],
];
