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
  /**
   * One or two plain words. This is a navigation label before it is a
   * heading — it sits in the sidebar rail, where a reader is scanning for
   * the thing they want, not reading sentences.
   *
   * These used to be clauses: "Factors, and whether they survived being
   * published", "Market breadth, and a warning that did not pay". Each was a
   * good line and a bad label, and the rail read as a paragraph broken into
   * links. The qualifier belongs in `standfirst`, which is right underneath
   * and already says it.
   */
  title: string;
  /** One line that answers "why does this section exist". */
  standfirst: string;
  body: string[];
  items?: { name: string; trust: Trust; detail: string }[];
  /**
   * Where a claim in this section came from, when it came from outside.
   *
   * Several sections rest on published work — the JKP factor series, the
   * Wasserstein regime paper, the small-cap case — and until now each was
   * named in prose with no way to reach it. A reference section whose whole
   * argument is "check this rather than trust it" should hand the reader the
   * thing to check.
   */
  sources?: { label: string; url: string }[];
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
    title: "Trust",
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
        name: "The five screens",
        trust: "computed",
        detail:
          "Every filter and every score is arithmetic over fetched fundamentals. No model reads a screen or ranks it. Results are computed ahead of time and served from a dated cache, so what you see is a list, not a request. The cache is dated twice over: once by the clock, and once by a fingerprint of the thresholds the screen applied, so a run scored under rules that have since changed says so instead of presenting itself as current. That second check exists because the first was not enough — adding a market-cap band to the compounder turned 398 of the 503 names in its cached S&P 500 run into companies that would now be rejected on size, and the file went on reporting them as passes dated that morning.",
      },
      {
        name: "Factors — JKP theme returns and where a company sits on them",
        trust: "computed",
        detail:
          "The theme and factor returns are Jensen, Kelly and Pedersen's published US series from jkpfactors.com, stored as a dated file; the Sharpe ratios and the in-sample/after-sample split are plain arithmetic over them. The company's tilt is a percentile rank against the cached screen universes. No model reads or writes any of it.",
      },
      {
        name: "Regimes — clustering whole return distributions, and a fitted chain",
        trust: "computed",
        detail:
          "Each quarter of returns is treated as a distribution and clustered in Wasserstein distance (Horvath, Issa and Muguruza, SSRN 3947905), rather than being reduced to a volatility number and thresholded. A hidden Markov model is fitted to the same returns by Baum-Welch, for the transition matrix the clustering cannot produce. No model is involved in any of it — language model, that is — and the same inputs always give the same labels. The tab scores all three labellings on the same windows with the same kernel, including the volatility rule it replaces, so the reader can see whether the regimes are real and which method found them. The chain's transition matrix is served on /api/regimes but is not yet drawn on the tab.",
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
        name: "Market breadth, and the forward returns after a divergence",
        trust: "computed",
        detail:
          "An advance-decline line, the share of members above their own 200-day average, and new highs less new lows, all built from 503 member price histories rather than read off a vendor's summary figure. The divergence test that follows — episodes, median forward returns, the unconditional comparison — is the same arithmetic. No model reads any of it, which is why the verdict can disagree with the chart.",
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
    id: "smallcaps",
    title: "Small caps",
    standfirst:
      "Why the desk is pointed at small and mid caps worldwide, and the figures that argument rests on — none of them computed here.",
    body: [
      "Everything else in this document is about how carefully the app handles a number. This section is the exception, and it is worth saying so plainly: every figure below comes from somebody else's research, not from anything this app computed. They are cited so you can check them, and they are the reason the desk is shaped the way it is rather than a claim it can defend from its own data.",
      "The case has three parts. The first is a valuation gap: the MSCI World Small Cap index has been trading around a 20% forward-earnings discount to the S&P 500, which is wide against prior regimes, and large-cap leadership cycles have historically run eleven to fifteen years before turning. The second is longer-run: small caps have outperformed large caps by roughly three to four times cumulatively since 1927. Neither is a timing signal, and the source says so — large-cap leadership can persist well past the point where it looks stretched.",
      "The third part is the one this app is actually built on, because it is the only one a single person can do something about. Roughly 18,000 listed companies worldwide have a market capitalisation under $10bn, representing about $30tn of market value, against something like $100bn of dedicated global small-cap mandates. Apple is followed by more than seventy analysts; a great many of these companies are followed by one or two. The inefficiency is not that small caps are cheap. It is that most of them are unexamined, and research organised country by country rarely compares two similar businesses competing in the same niche from different domiciles. That gap is reachable by one person with a screen and a method, and it is not reachable in large caps at any effort.",
      "The same research also explains why this desk screens for quality rather than merely for size, which is the distinction that matters most here. Around 40% of the Russell 2000 has no earnings at all. Profitable US small caps returned roughly 14% annualised since 1963 against about 9% for unprofitable ones, and over 2004–2024 profitable Russell 2000 constituents beat the loss-makers by around 6.5% a year. Small caps misprice weak businesses as readily as strong ones, so 'small' on its own is not an edge — it is a wider distribution. The compounder screen's return-on-capital floor, cash-conversion test and reinvestment runway all exist to stand on the right side of that split, and the market-cap band exists so the screens are actually pointed at the shelf where the coverage gap is.",
      "Read it as a thesis with a counterargument attached, not as a finding. The app computes nothing in this section and cannot check any of it.",
    ],
    sources: [
      {
        label: "The case for global small-cap equities — Hedge Fund Alpha",
        url: "https://hedgefundalpha.com/news/the-case-for-global-small-cap-equities/",
      },
    ],
  },
  {
    id: "principles",
    title: "Principles",
    standfirst:
      "What this desk will and will not own, separated by whether a machine can actually check it.",
    body: [
      "Most of this existed before it was written down. A commodity avoid-list sat inside one screener's regex, a size band inside another's constants, a concentration ceiling in the sizing module. Each arrived as a threshold in a function rather than as a choice, which meant the desk's philosophy could not be read without reading six files, and nothing stopped two of them from disagreeing.",
      "They are now registered in one place, and — this is the part that matters — each one is tagged with how it is enforced. A universe rule is checked when a universe loads. An exclusion is matched against the sector and industry a company reports. A threshold is a bar a screen computes, and is covered by the criteria fingerprint so that moving it invalidates every cached run. A judgment is something true that no feed can check.",
      "That fourth kind is the one most often faked. 'A defensible position in a niche' and 'management who treat minority holders fairly' are the two most load-bearing judgments in small-cap investing, and neither can be read off a data feed — a sector code is not a market share, and an aggregate insider percentage does not identify a founder. They are registered as explicitly unenforceable, handed to the committee, and recorded on every screen row as not checked. Scoring them would produce numbers that look exactly like the measured ones, which is the single thing this whole application is built to prevent.",
      "Three standing exclusions are applied before any company is measured, across every screen: vice, defence, and fossil-extraction. These are ethical lines rather than analytical ones — gambling and tobacco businesses in particular score well on nearly every measure here, which is precisely why the rule has to stand rather than be re-decided each time a cheap one appears. The defence pattern knowingly over-reaches: the standard label is 'Aerospace & Defense' and it is excluded whole, which also removes civil aerospace suppliers. A screen row says which principle removed it, because 'excluded' with no reason is indistinguishable from having failed on the arithmetic.",
      "One principle is deliberately registered as NOT enforced. This desk only looks at developed markets with reliable disclosure, and that is true today purely because the eight universes happen to be the US, Japan, the UK, Germany, Canada and Australia. It is a description of the current state, not a rule, and adding one emerging-market universe would end it with nothing to catch the change. Recording it as a judgment rather than as a universe rule is the honest option; claiming a check that does not run is the same defect as a screen that reads as large-cap only because of its default universe.",
      "The exclusions match reported sector and industry labels, not revenue. A conglomerate earning a fifth of its profit from tobacco through a subsidiary classified as Packaged Foods will not be caught. This is a coarse instrument that removes the obvious cases, and it should not be described as more than that.",
    ],
  },
  {
    id: "pipeline",
    title: "Method",
    standfirst:
      "The model appears twice, in two narrow roles, and is the source of no figure in between.",
    body: [
      "Market data is fetched once and frozen, so every stage downstream reads the same content-addressed snapshot. The planner turns the question into a typed plan. The executor computes every figure in Python. A narrator writes prose over those results. The harness then validates the output, verifies each numeric claim, and overrides the conviction score with the computed one where a plan produced it. The run is persisted whole — snapshot, prompts, model parameters, output — so two runs can be compared rather than argued about.",
      "The order matters more than the parts. Handing a model a pile of data and asking for a verdict makes every figure in the answer a token prediction. Splitting the choice of measurement from the measurement itself means a wrong answer can be traced to either a bad plan or bad data, and fixed at the method level instead of being corrected number by number.",
    ],
  },
  {
    id: "screens",
    title: "Screens",
    standfirst:
      "Each one is a different question, pointed at the universe and the market it was designed for.",
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
          "Size, growth, return on invested capital, cash conversion, leverage, margin trend and dilution as hard filters, then a ten-factor score out of 50. Bounded to roughly $500m–$20bn in the currency the company reports in. The tenth factor is Akre's reinvestment runway — the reinvestment rate multiplied by the return on incremental capital, which is what the business can compound at from its own cash. Organic growth is a revenue proxy, not a reported figure, so a company growing purely by acquisition can read as organic — check the segment disclosures.",
      },
      {
        name: "Bolton contrarian — S&P 500",
        trust: "computed",
        detail:
          "Anthony Bolton's special-situations framework, automated as far as it honestly goes: cheap on at least one multiple, sitting low in its own 52-week range, and generating enough cash to survive the wait. Scored out of 100 across valuation, neglect, balance sheet, insider buying and whether the fall has stopped.",
      },
      {
        name: "Kiyohara handbook — Japan mid & small",
        trust: "computed",
        detail:
          "Tatsuro Kiyohara's own checklist, which is one page of the Japan Company Handbook: the P/E on the second-year forecast, the equity ratio, net cash against market value, and whether the company has ever issued equity to fund itself. Scored out of 100. It runs on TOPIX Mid400 plus Small 1, sourced from the Tokyo exchange's own listing file, because the framework is about Japanese ownership and would still produce a plausible-looking list anywhere else.",
      },
      {
        name: "Ellenbogen two-act — S&P SmallCap 600",
        trust: "computed",
        detail:
          "Henry Ellenbogen's compounder framework, scored out of 100: size inside the $1bn–$20bn band his own study starts compounders in, revenue on a 20% path and still growing, a core that already earns money at the size it has reached, and — the trait his research actually found — a return on invested capital that rises as the business gets bigger. Owner alignment and gross-margin trend carry the rest. It runs on the small-cap index because about 80% of the roughly 40 companies that compound at 20% in any decade begin that run there.",
      },
    ],
    body: [
      "The Bolton screen is deliberately incomplete, and the gap is the most important thing about it. His framework has five sections and only four can be computed. The fifth is the catalyst — a restructuring, a hidden asset, a legal overhang lifting, an earnings inflection still priced as decline — and that is the section he says separates a re-rating from a value trap. It cannot be read from a data feed.",
      "So the screen does not score it and does not pretend to. Every row it returns records that the catalyst was never checked, and by Bolton's own reasoning a name that passes is a value trap until someone finds one. That judgment is the Bolton persona's job on a company's own page, which is why the screen's output links there instead of ending in a verdict.",
      "The Kiyohara screen has the same shape of hole in two places. His P/E ceiling depends on what kind of business it is — 20x for high share of a global niche, 15x for a long and credible customer list, 10x for small or mid-cap real estate, 7x for a subcontractor living off three customers — and a data feed carries a sector code, not a market share. So the screen reports which of the four ceilings a name is under and records that the business type was never checked; real estate is the one tier the sector code settles, and that 10x is enforced. The second hole is the shareholder register: the Handbook names the founder's family, and the trade he described turns on inheritance tax eventually forcing that stake to move. The feed gives one anonymous insider percentage, so the screen says 'closely held' at most and never claims to have found the founder.",
      "What it deliberately does not look at is also his: no dividend, no price chart, no broker ratings. He says to ignore them, so nothing in the screen reads them, and a test fails if a field for any of them ever appears.",
      "The Ellenbogen screen is the third version of the same honesty, and the largest hole of the three. His framework splits a company into two acts: Act 1 is proven product-market fit, a large addressable market and unit economics that work, and Act 2 is the leap to a significant new product or market that makes it fundamentally larger. Act 1 leaves a financial trace and that trace is what is scored. Act 2 is a judgment about a product that does not exist yet and a management team's appetite for a hard transition, so every row records that it was never checked — along with whether this is a founder on their second act, which is what he actually selects on and which no feed carries.",
      "Two choices inside it are worth knowing about. The scored trait is the slope of return on invested capital rather than its level, because his research found compounders that got better as they got bigger, and a high flat return is a good business rather than a compounder. That slope is reported as unmeasured, and scored neutral, when it would be an artefact: revenue that did not actually grow, or a capital base shrinking under a buyback, which lifts the ratio with no operating improvement at all. And the drawdown from the five-year high is reported but never scored. His study found a compounder falls about 62% in one of its ten good years, usually during the transition, so a deep fall on a financially intact business is flagged as a transition candidate — which marks where his question gets asked, not an answer to it. Scoring it would turn a quality screen into a falling-knife screen.",
    ],
  },
  {
    id: "investors",
    title: "Investors",
    standfirst:
      "Seventeen investors are available; seven speak by default, chosen to disagree for different reasons.",
    body: [
      "Each investor is a prompt built from a stored profile: who they are, how they think, and the concrete tests they apply. The app shows you those tests next to their verdict, and both come from the same source — a description kept separately from the instruction would eventually tell you an investor weighs one thing while the model had been told to weigh another.",
      "The default committee is Buffett, Munger, Lynch, Fisher, Li Lu, Lou and Kiyohara. Each covers an axis the others do not: durable economics at a sensible price, the inversion of what would make it a bad business, growth a generalist can actually understand, the qualitative checks no feed carries, a concentrated owner's view, deep work on very few names, and the Japanese small-cap register and balance sheet. Four of the seven made their records outside the United States, which matters on a desk that screens eight universes across six currencies. A committee of near-duplicates produces a confident consensus that reflects one way of looking, which is worse than a narrower claim honestly made.",
      "It used to be Buffett, Graham, Wood, Burry, Bolton, Druckenmiller and Damodaran, which was the right committee for a different desk. Three of those seven answered questions this one does not ask — what is the disruption thesis, what is the liquidity regime, what does the multiple imply — and two of the three were top-down voices reviewing a bottom-up screen. All seventeen investors are still there and still individually selectable; this is only who speaks when you do not choose.",
      "Read the spread, not the average. Seven investors agreeing tells you less than two of them disagreeing for a reason you had not considered.",
    ],
  },
  {
    id: "lookback",
    title: "Portfolio",
    standfirst: "Every figure on that screen is measured, not forecast.",
    body: [
      "Weights, expected returns, volatilities and the correlations the weights are derived from are all computed over one historical window, and nothing outside it. The screen draws that window as a dated bar with an arrow pointing into the past, because a table of two dates makes the reader do the subtraction and a backtest read as a forecast is the most expensive misreading available here.",
      "Two years of history and ten are different claims. Where the requested window is longer than the shortest price history in the basket, the window silently shortens for everything — so the shortfall is stated rather than left to be noticed.",
    ],
  },
  {
    id: "factors",
    title: "Factors",
    standfirst:
      "A century of factor returns from the replication-crisis paper, and one company placed on them.",
    body: [
      "The Factors tab under Analysis draws the thirteen themes of the Jensen–Kelly–Pedersen dataset — value, momentum, quality, profitability, investment, low risk, low leverage, size, accruals, debt issuance, profit growth, short-term reversal and seasonality — from their US, monthly, capped value-weighted long-short portfolios back to 1926. The returns are theirs, reshaped by scripts/refresh_jkp.py into a committed file that records the last month it covers, so the tab works offline and never silently changes between two page loads.",
      "Pick a theme and every factor inside it is split around the years its original paper studied: a Sharpe ratio inside that sample, and one after it ended. That is the paper's own question — does a published anomaly keep working once it is known — asked factor by factor. Most shrink; the bar is whether the return stayed positive, not whether it stayed the same size.",
      "The company's tilt is this app's own measurement, not JKP's. Each characteristic it can compute from the fetched fundamentals is ranked against whichever of the four screen caches' 1,980 names carry that field, which is between about four hundred and eleven hundred of them depending on the field — the Japanese cache stores market capitalisation and balance-sheet lines but no trailing income or cash flow, so it supplies peers to one characteristic and none of the rest — flipped where JKP buy the low end so that above 50 always means the side the factor buys, and averaged into its theme. Approximations are marked where they differ from JKP's definition, and a theme with nothing measurable is left blank rather than shown as a neutral 50.",
    ],
    sources: [
      {
        label: "Jensen, Kelly & Pedersen — Global Factor Data",
        url: "https://jkpfactors.com/",
      },
    ],
  },
  {
    id: "regimes",
    title: "Regimes",
    standfirst:
      "Clustering whole return distributions instead of thresholding a volatility ratio, a fitted chain for the question clustering cannot answer, and a score that says whether any of the three divisions hold.",
    body: [
      "The Regimes tab under Analysis cuts a company's price history into overlapping windows of about a quarter, treats each window as a distribution of daily returns rather than as a set of summary statistics, and clusters those distributions in 1-Wasserstein distance. The method is Horvath, Issa and Muguruza (SSRN 3947905). In one dimension the optimal transport problem has a closed form — sort two windows and average the absolute differences — so this is ordinary numpy and needs no solver, and a regime's centre is the pointwise median of its members, which is why a single crash window cannot drag it.",
      "It replaces a rule that compared recent volatility to a longer baseline and cut the ratio at 1.25. That rule used one moment and two thresholds nobody derived. On synthetic paths where the regime changes are planted and therefore known, clustering distributions catches substantially more of them than the ratio does, and the gap widens when returns jump — which is the case real equity returns resemble. Those paths are in tests/test_regimes.py as an accuracy floor, because real market data has no answer key and any accuracy figure quoted on it is either circular or someone pointing at a chart.",
      "The first thing on the tab is not the regimes but the separation ratio, because any clustering returns clusters: ask k-means for two groups and it produces two, whether or not two exist, and the resulting chart is equally convincing either way. The ratio measures how much more a window resembles its own group than the other, using a maximum mean discrepancy two-sample statistic. Above 1 the split means something; at or below 1 it is one population cut in half. The same score is computed for the volatility rule and for the hidden Markov labelling on identical windows with an identical kernel, and shown beside it — including on the names where the old rule wins. A labelling whose windows all fall into one group cannot be scored at all, which is the usual outcome for the chain, and the tab says so rather than printing a number.",
      "The clustering is fitted over the whole period at once, so every label was assigned knowing what came after it. That limit is structural rather than temporary: this describes where a company has been, and must not be backtested on or treated as a signal.",
      "Clustering also cannot be asked how long a regime lasts, because it treats the windows as an unordered bag — shuffle the history and the labels come back identical. Every question about order is therefore unanswerable in that model: how long these stretches run, whether turbulence follows turbulence, what the odds are that this one is over. So a hidden Markov model of the same returns is fitted beside it, by Baum-Welch with Gaussian emissions, and the response carries what only a transition matrix can give — each state's persistence, the run length the fitted chain implies, and the share of tomorrow the last day's posterior pushes onto each state. Those three figures are computed and returned by /api/regimes; the tab currently draws only the chain's separation score next to the other two, so for now they are an API answer rather than something on the page.",
      "That last number is the one to be careful with. It is a description of the fitted history, not a forecast, and the chain it comes from is the weakest detector of the three on the paths where the answer is known: a Gaussian cannot jump and equity returns do, so maximum likelihood prefers to widen one state's variance over spending a transition. That is what tests/test_regimes.py pins — the clustering beats the chain on synthetic paths with planted regime changes — and it is pinned so no later change can quietly promote it. On a real history the chain often cannot be given a separation ratio at all, because its turbulent state is a one- or two-day bucket that never wins a whole window. Read it for the shape of the chain, not for where the market goes next.",
    ],
    sources: [
      {
        label: "Horvath, Issa & Muguruza — Clustering Market Regimes (SSRN 3947905)",
        url: "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3947905",
      },
    ],
  },
  {
    id: "macro",
    title: "Macro",
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
    id: "breadth",
    title: "Breadth",
    standfirst:
      "The index at a high while half its members are below their own trend \u2014 measured exactly, then checked against what actually followed.",
    body: [
      "Market breadth is the one screen here that is about the market rather than about a company, and it exists because of a specific and very old claim: that an index making new highs on a shrinking number of participating stocks is a warning, and that this warning preceded the crashes of 1929, 1962, 1973 and 1987. The measurement half of that claim is arithmetic. Three measures are built from the index\u2019s members \u2014 a cumulative advance-decline line, the share trading above their own 200-day average, and new 52-week highs less new lows \u2014 and the signal is deliberately crude: the index within a couple of percent of its one-year high while fewer than half its members are above their 200-day average. A divergence that needs a clever definition to appear is not the thing the warning is about.",
      "The predictive half is an empirical question, and it is answered on the same screen rather than assumed. Signal days arrive in clumps, so they are collapsed into episodes and forward returns are measured once per episode \u2014 counting a forty-day run as forty observations is the commonest way this kind of study is overstated. Across every threshold setting offered, the index\u2019s median return after a divergence has not been worse than its unconditional return over the same history, and at most settings it was better. The verdict says so in those words, above the chart rather than below it, because a divergence chart is extremely persuasive to look at and that is precisely the problem with it.",
      "Three reasons that finding may itself be wrong, none of which the screen can rule out. Breadth is measured across the index\u2019s current members carried backwards, so every company that fell out of the index after falling is missing and past breadth is flattered. The history starts in 2004, which contains two bear markets and none of the episodes the warning was built on \u2014 no free source of index membership reaches 1962. And a signal that fires a handful of times cannot be separated from noise by its own hit rate, in either direction. The episode count sits beside every median for that reason.",
      "The thresholds are controls rather than constants. Neither is derived from anything \u2014 both are conventions \u2014 and the episode count moves by an order of magnitude across the range offered, which is the most useful thing on the screen. The five hundred price histories behind it are built ahead of time by scripts/refresh_breadth.py and served dated, so the page answers instantly and says how old it is.",
    ],
  },
  {
    id: "autoresearch",
    title: "Autoresearch",
    standfirst:
      "The searcher only ever sees the in-sample window. The out-of-sample window decides.",
    body: [
      "One strategy is proposed at a time, fitted on one window, and judged on a window it never saw. The bar rises as more variants are tried, because searching enough rules against a single price history will always turn something up. Discarded runs stay on the log, since a leaderboard of survivors is how a search process starts looking skilful.",
      "The chart on that page draws one line per experiment, from where it was fitted to where it was tested. Almost every line runs the wrong way. That is the finding, and it is the reason to distrust any backtest — including the ones here — that is presented without its out-of-sample leg.",
    ],
  },
  {
    id: "data",
    title: "Data",
    standfirst: "Several providers, which disagree with each other.",
    body: [
      "Market data comes from keyless providers by default, with fallback and caching, and every fetch records who answered, whether it came from cache, and how the payload verified — frequency, coverage, units. Providers disagree on split adjustment, fiscal alignment and currency, so knowing which source answered is part of reading the number.",
      "The model runs locally through Ollama; the portfolio lives in a SQLite file you own; no API keys are required. Optional keys add coverage. A stage can be pointed at its own model, so bulk work and the hardest judgment step need not use the same one.",
      "Screens are pre-computed and dated. They read quarterly fundamentals, so a run is wrong the moment a company reports — the age is shown next to every list, and past a week it says so in colour.",
      "A refresh now probes the data provider before it starts, and reports one of three states: ok, degraded, or offline. Offline means the provider answered for nothing — so the run does not start and the existing cache is left alone, rather than being overwritten with a complete-looking list that is missing an eighth of its names. That is not hypothetical: it is what happened before the probe existed.",
      "The committee's investor calls run one at a time, not in parallel. The local model server serialises them, so a seven-member run costs roughly seven times one call — about a minute and a half. Measured, not estimated.",
    ],
  },
  {
    id: "membership",
    title: "Access",
    standfirst:
      "Invite-only is built and not yet switched on. The reason for it is the model bill, not exclusivity for its own sake.",
    body: [
      "Run locally, none of this applies: the model is Ollama on your own machine, the portfolio is a SQLite file you own, and there is no gate, no member and no allowance. Everything below describes the hosted deployment only, and it is switched off by default in the code.",
      "On the hosted site the model provider is a paid gateway, so the four routes that invoke a model bill whoever deployed it. Left open, those routes are an anonymous proxy with somebody's card behind it — which is why they have run switched off entirely rather than being left reachable. Membership is what would let them come back on: a named member carries a monthly token allowance, so a seat is a known cost rather than an open one.",
      "Both switches live in the deployment's environment, not in the code, so this page cannot be the authority on them — ask `GET /api/me`, which reports both. When this was last checked it answered `gate_enabled: false, llm_enabled: false`: nobody is a member, the hosted site asks for no invite, and the four model routes refuse everyone. The code's own defaults differ from that, so a flipped variable makes this paragraph stale with nothing failing. They are two separate switches on purpose — one says 'this deployment runs no models', the other says 'and only members may call anything' — and the order to turn them on is gate first, models second, because the reverse is an open gateway for however long it takes to notice.",
      "Access works by single-use invite link, sent by someone already inside. There is no sign-up form and no waitlist. The link carries its key in the URL fragment rather than the path, so the key is never transmitted to the server and never appears in an access log; the page strips it from browser history as soon as it has been read. An invite opens exactly one session and is then spent, and it can be withdrawn before it is used.",
      "Allowances are counted in tokens, per UTC calendar month, summed from the provider's own reported counts after each call. A member's own usage is shown in the app chrome as a percentage, because a cap you cannot see is a trap whose first symptom is a refusal in the middle of an analysis. Two refusals are deliberately distinguishable: running out of monthly allowance is not the same as hitting the per-hour rate limit, and only one of them is worth retrying.",
      "Dollars are not tracked here. A per-model price table drifts silently as a gateway changes its rates, and a plausible-looking cost that is quietly wrong is exactly the kind of number the rest of this app exists to avoid. The gateway's own dashboard is the source for money; this ledger counts tokens, which is what the allowance is denominated in.",
      "What revocation does and does not reach: withdrawing a member closes their open sessions immediately, including a tab that was already loaded, because sessions are database rows rather than signed tokens. What it cannot undo is spend that has already happened.",
    ],
    items: [
      {
        name: "Invite admission — single-use, at most once",
        trust: "computed",
        detail:
          "An invite is claimed by one conditional UPDATE, and admission requires it to have changed exactly one row. Two simultaneous clicks on a forwarded link therefore admit one person, not two — a check-then-write would admit both.",
      },
      {
        name: "Monthly token allowance",
        trust: "computed",
        detail:
          "Summed from the provider's reported prompt and completion counts since the first instant of the current UTC month. Checked before a model is called, so a member at their cap costs nothing.",
      },
      {
        name: "Allowance overshoot",
        trust: "written",
        detail:
          "Counts exist only after a call returns, so one in-flight request can cross the line and a gateway timeout can bill without reporting anything. The overshoot is bounded by a single call; the ledger can undercount by the failure rate. Neither is estimated or corrected for.",
      },
      {
        name: "Per-member cost in dollars",
        trust: "written",
        detail:
          "Recorded only when the gateway itself reports a cost, and left empty otherwise. There is no local price table, so this column is blank rather than guessed.",
      },
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
    "A leaked invite link is a seat",
    "An invite is a bearer capability: whoever opens the link first becomes the member, and there is no second factor behind it. Single use, a short expiry and the ability to withdraw it bound the damage; they do not prevent it. At this size that is a deliberate trade, not an oversight.",
  ],
  [
    "No screen checks a catalyst",
    "The Bolton screen is explicit about it, but it applies to all four: a passing name is a candidate for a question, not an answer to one. Nothing in the app can see a restructuring, a spin-off or a legal overhang lifting.",
  ],
  [
    "Committee conviction is not reproducible",
    "Investor analyses run with full freedom rather than as weightings over computed dimensions. Their conviction scores will move between runs. The plan pipeline's will not.",
  ],
  [
    "The published site does not run the model",
    "Four things here invoke a language model: researching a ticker, the plan pipeline, the backtest, and the autoresearch loop. Those run on your own machine against your own Ollama, which is why they are free and why nothing about your book leaves your computer. The hosted deployment's provider is a paid gateway instead, so all four are switched off there and answer 503 with a sentence saying why. Membership is what would let them back on, under a per-member allowance; it is not switched on yet, so today the published site runs no model for anyone, member or not.",
  ],
  [
    "And most of its data is not shipped either",
    "Every one of these files is committed, but only two of the four directories are copied into the deployed image: the JKP factor returns and the macro news series, which is why the Factors and Macro tabs answer on the published site. The screen caches and the breadth series are left out of the image deliberately, so a visitor gets an empty screen list and a breadth page that says it has not been built. The company tilt on the Factors tab needs the screen caches for its peers, so it is absent there too. What the published site is for is the landing page, the methodology and this reference.",
  ],
  [
    "Only the single-investor path is measured",
    "Twenty cases with pass/fail rules score one investor at a time against frozen company snapshots: whether the answer is well-formed, whether its figures come from the data it was given, and whether the investor's own framework actually applied. The committee — where investors read each other and can revise — is not covered, and it is the path where a prompt change turned the designated bear from a strong sell into a strong buy. Treat a passing score as evidence about one analysis, not about the committee's spread.",
  ],
  [
    "The factor tilt measures less than JKP do",
    "JKP sort on 153 characteristics from CRSP and Compustat. The tilt uses about twenty that the screen caches can supply, some approximated (a six-month return that does not skip the latest month, a five-year sales growth standing in for three), and four themes — low risk, debt issuance, profit growth and seasonality — cannot be measured at all. Peers are whatever the screen caches hold for that characteristic: between about four hundred and eleven hundred US names, median under six hundred, and 1,974 for market capitalisation — the one field the Japanese cache also supplies — not JKP's full sample, and on the hosted site there are no caches, so there is no tilt. Accounting ratios also mean something different for banks and insurers, which sit in the same ranking.",
  ],
  [
    "One factor characteristic is currently wrong, by a lot",
    "The peer ranking pools every screen cache into one cross-section, and the Japanese cache stores market capitalisation in yen while the US ones store dollars. Nothing converts them. Market equity is the one characteristic read as a raw currency amount rather than a ratio, so every one of the 872 Japanese names outranks the 791 smallest of the 1,102 US names on it — the bottom 72% — and a $44bn US company ranks at the 44th percentile of size in the pooled list where it is really at the 77th. JKP go long the small end, so the flip turns that into a large company reading as a small one, and the error carries into the Size theme average. Every other characteristic is a ratio and is unaffected. This is a defect with a known fix, not a limit of the method — until it lands, read the Size theme on a US company as unreliable.",
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
    "The regime clustering is fitted over the whole history at once, so each label used the data around it, including later data. It is descriptive only, and cannot be traded on. Choosing how many regimes to fit is also a setting rather than a finding, not least because the same k is handed to the clustering and to the chain.",
  ],
  [
    "The chain's next-day number is the most misreadable figure here",
    "The hidden Markov model is fitted on the whole series too, so its transition matrix is in-sample, and it is the weakest of the three labellings on this app's own separation score — the Gaussian emission cannot represent a jump, which is most of what matters in equity returns. Its persistence and expected run length describe the history it was fitted on. The share of tomorrow it puts on each state is one step of that same matrix applied to the last day's posterior: a restatement of the fit, not a prediction, and it is reported next to how sure the model is that it has even got today right.",
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
    "Only eight universes load",
    "The S&P 500, MidCap 400 and SmallCap 600; TOPIX Mid400 and Small 1 as one Japanese band; the FTSE 250 and the MDAX; and every listed company on the Toronto and Australian exchanges. Four of the eight come from an exchange's own file. The NASDAQ-100, Dow and Russell 2000 loaders all broke upstream when their sources changed shape, and were removed rather than left as options that can only fail — so did the Nikkei 225, which is why Japan comes from the Tokyo exchange's own listing file instead of a third party's rendering of one. Three more were probed and refused for the same reason: the SDAX article lists German small caps with no ticker column, the STOXX Europe 600 table renders 467 of 600 constituents without saying so, and the Indian index publisher answers its own constituent file with a 403. Every market outside those eight is a short curated watchlist, not an index.",
  ],
  [
    "The second act is the whole judgment and no screen makes it",
    "Three of the five screens are missing their most important section by construction, and each says so on every row. Bolton's catalyst, the Kiyohara P/E tier and the founder's stake, and Ellenbogen's Act 2 all need a person to read a business rather than a feed to return a field. A name that passes any of those screens has cleared the arithmetic half of a framework whose author says the other half is what decides the answer.",
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
