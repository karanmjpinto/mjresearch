/**
 * Every term the app uses that a reader could reasonably not know.
 *
 * One file, for two reasons. The same word appears on four screens and has to
 * mean the same thing on all of them; and a definition written next to the
 * component that needs it gets copied, drifts, and ends up contradicting
 * itself. Improving an explanation should be one edit.
 *
 * Each entry has up to three parts, in the order a reader needs them:
 *
 *   what      the plain definition, no jargon used to define jargon
 *   why       why it is on the screen at all — what it changes
 *   careful   the trap. Usually the most valuable line: a definition says
 *             what a number is, this says how it misleads.
 *
 * `careful` is optional and should stay that way. Adding one to every term
 * makes the reader stop reading them.
 */

export type GlossaryEntry = {
  term: string;
  what: string;
  why?: string;
  careful?: string;
};

export const GLOSSARY = {
  // ── The dashboard ──────────────────────────────────────────────────────
  "book-value": {
    term: "Book value",
    what: "What everything you hold is worth right now, at the latest prices, plus uninvested cash.",
    why: "Every position size on the Play it stage is a share of this number, so it is the denominator for the whole app.",
    careful:
      "Holdings priced in another currency are left out rather than converted at an invented rate, so this can be smaller than your real book. The portfolio screen names any that were excluded.",
  },
  "data-providers": {
    term: "Data providers",
    what: "How many of the market-data sources this app knows about are actually working right now, out of how many it could use.",
    why: "A missing provider is why a number is blank rather than wrong. The stack list says which ones answered.",
    careful:
      "Configured is not the same as good. A provider with an expired key counts as configured and still returns nothing.",
  },
  "sector-drift": {
    term: "Sector drift",
    what: "Which parts of the market are moving, best to worst — technology, energy, healthcare and the other eight.",
    why: "A company's move is often just its sector's move. Seeing the sector first tells you whether you are looking at news about the business or about the weather.",
    careful:
      'Computed from the eleven S&P 500 sector ETFs, so it is large-cap total return, not the whole market. "Sector performance" elsewhere often means the average across every listed company, which is a different number and usually much higher.',
  },
  "run-locally": {
    term: "Runs on this machine",
    what: "The model that writes the analysis runs on your own computer through Ollama. No API key, and nothing about what you research is sent anywhere.",
    why: "It is why the analysis takes twenty or thirty seconds rather than two: your machine is doing the thinking.",
    careful:
      "It also means the answer depends on your hardware and which model you pulled. A different model gives a different view of the same numbers.",
  },
  watchlists: {
    term: "Watchlists",
    what: "Named groups of tickers you want to come back to, kept in a plain file at config/watchlists.json.",
    why: "A quick way into a set of names without typing each one — the regional lists are there because coverage differs by market.",
  },
  "recent-research": {
    term: "Recent research",
    what: "Every analysis run you have done, newest first, with what it concluded.",
    why: "Each row is a saved snapshot: the data as it was, the plan that ran, and the verdict. You can come back and see whether the reasoning held, not just whether the price moved.",
  },
  "decision-log": {
    term: "Decision log",
    what: "The calls you actually recorded — buy, hold or sell — with the price at the time and the reasoning attached.",
    why: "This is the only honest scorecard. A view you remember having is not evidence; a dated note saying what you expected and why is.",
    careful:
      "The point at review is whether the argument held, not whether the price went up. A right call for a wrong reason is a loss waiting to happen.",
  },

  // ── The stages ─────────────────────────────────────────────────────────
  "stage-data": {
    term: "Data",
    what: "Everything measured about the company: fundamentals, price technicals, alternative data, peers, backtests, sentiment, macro and institutional ownership.",
    why: "Kept apart from Analysis on purpose. This stage is what was counted; the next one is what somebody made of it.",
  },
  "stage-analysis": {
    term: "Analysis",
    what: "What the model makes of the company — read through named investor styles, then checked against the numbers it used.",
    why: "It starts on its own when you open a ticker, because opening a company is the request.",
    careful:
      "The model produces no numbers itself. Every figure comes from Python; the model only chooses which to compute and writes the prose, and the Evaluation tab shows where its words disagreed with its own data.",
  },
  "investor-views": {
    term: "Investor views",
    what: "The same snapshot read through different well-known investing styles, then reconciled by a portfolio-manager pass.",
    why: "Disagreement is the useful output. When Graham and Wood reach the same verdict on a name, that is worth more than either one alone.",
    careful:
      "These are styles, not the people. Nobody named here has seen this analysis or endorses it.",
  },
  evaluation: {
    term: "Evaluation",
    what: "Which metrics the model chose to compute, what each returned, and whether the prose it wrote actually agrees with them.",
    why: "A model that writes a confident paragraph citing a number it never computed is the main failure mode here. This is how you catch it.",
  },
  factors: {
    term: "Factors",
    what: "The thirteen themes of the Jensen–Kelly–Pedersen factor dataset — value, momentum, quality, low risk and the rest — with a century of their returns, and where this company sits on each.",
    why: "It says what kind of company the investors are arguing about, in the vocabulary the research uses, and whether that kind of company has been paid for being one.",
    careful:
      "The only tab here with no model in it. The returns are the authors' published data; the company's position is computed by this app and uses fewer characteristics than they do.",
  },
  "factor-tilt": {
    term: "Factor tilt",
    what: "For each theme, where this company ranks among about eleven hundred S&P 500 and SmallCap 600 names on the characteristics JKP sort on — 0 to 100, with 50 the middle. Above 50 is the side the factor buys.",
    why: "A factor portfolio is long one end of a ranking and short the other. A rank is the honest single-company reading of that.",
    careful:
      "Some characteristics are approximations and several themes cannot be measured from this data at all; those are left blank, not set to 50. A tilt describes the company. It is not a forecast that the premium arrives for it.",
  },
  "factor-replication": {
    term: "Survived its paper",
    what: "Each factor's Sharpe ratio inside the years its original paper studied, against the years after that sample ended.",
    why: "The question JKP's paper is named for: does a published anomaly keep working once it is known? A factor that only worked in-sample was a finding about the data, not about markets.",
    careful:
      "Most premiums shrink after publication, and that is expected — the bar is whether the return stayed positive, not whether it stayed the same size. A shorter post-sample window is a noisier one.",
  },
  "signal-intelligence": {
    term: "Signal intelligence",
    what: "Where the model's view sits against the analyst consensus and the news sentiment.",
    why: "Agreeing with everyone is not an edge. This shows whether the conclusion is contrarian or crowded.",
  },
  conviction: {
    term: "Conviction",
    what: "How strongly the case holds together, 0 to 100.",
    why: "It decides how big a position is allowed to be. Low conviction is not a criticism — a diversified book is the correct response to not having one.",
    careful:
      "Three things must all hold: you have an edge, there is a reason the market corrects, and it corrects inside your horizon. They multiply, so one weak leg caps the whole score — a blank leg is not a low score, it is an unanswered question.",
  },
  "stage-lens": {
    term: "Your lens",
    what: "What you have already written about this company, from your own Obsidian vault.",
    why: "Your notes are the one input here nobody else has, which makes them the only realistic source of an edge that is not already in the price.",
    careful:
      "Nothing leaves your machine, and nothing is written to your vault without a press.",
  },
  "frameworks-run": {
    term: "Frameworks, run",
    what: "Your own checklists, with this company's figure next to each line.",
    why: "Being told a checklist is relevant is a reminder. Seeing the number against each line is an answer.",
    careful:
      'A line that asks for a view — "is management honest" — comes back as "your call" rather than a tick, and a line with no matching figure comes back as "no figure". Neither is a fail.',
  },
  "one-pager": {
    term: "One pager",
    what: "A page for this company, drafted in your own template and written back into your vault.",
    why: "The conclusion ends up where you will look for it, linked to the notes that matched, instead of in a browser tab you close.",
    careful:
      "It never replaces an existing note. If a page is already there it refuses, because anything you added by hand exists nowhere else.",
  },
  "stage-play": {
    term: "Play it",
    what: "How to express the view and how big to make it, against the book you already hold.",
    why: "A good company is not a good position if you already own three of them. This sizes against what is there.",
  },

  // ── Value & risk ───────────────────────────────────────────────────────
  "value-per-share": {
    term: "Value per share",
    what: "What the four drivers imply one share is worth, before comparing it to the price.",
    careful:
      "It is an output of your assumptions, not a fact about the company. Change the growth rate and this changes; the market did not move.",
  },
  "median-upside": {
    term: "Median upside",
    what: "The gap between the middle of the simulated values and today's price, as a percentage.",
    why: "The median rather than the base case, because the base case is one draw and the median is where half the draws landed.",
  },
  "draws-above-price": {
    term: "Draws above price",
    what: "Out of ten thousand simulated valuations, how many came out above what the market is asking.",
    why: "A cleaner question than a single fair value: a name where 2% of draws clear the price is a different proposition from one where 60% do, even if both medians are the same.",
  },
  "terminal-share": {
    term: "Terminal share of value",
    what: "How much of the total value sits in the years after the forecast ends, rather than in the ten years modelled.",
    careful:
      "A high share is not an error, but it means the answer is mostly a claim about the distant future. Above roughly two thirds, you are valuing a perpetuity with a ten-year preamble.",
  },
  "cost-of-capital": {
    term: "Cost of capital",
    what: "The return this company has to earn for its money to have been worth raising — built up from the risk-free rate, its beta, and the equity risk premium.",
    why: "It is the rate every future cash flow is discounted at, so it moves the answer more than almost anything else.",
    careful:
      "Built up step by step rather than asserted, so each piece can be argued with separately. Where a piece is missing — usually interest coverage — it is left out and named, not guessed.",
  },
  "the-range": {
    term: "The range",
    what: "Each driver is drawn repeatedly within a spread and the model re-run every time, giving a distribution of values rather than one number.",
    why: "The width is the answer. A company whose plausible values run 90 to 160 is a different proposition from one that lands on 124 every time.",
    careful:
      "The drivers are drawn independently, which makes the range slightly wider than reality — growth and margin move together in practice.",
  },
  "market-implied": {
    term: "What the price implies",
    what: "The value this one driver would have to take for the model to agree with today's price, holding the others where they are.",
    why: "This is the anchor. It turns a blank box into a position: above the implied figure you are more optimistic than the market, below it more sceptical.",
    careful:
      "Solved one driver at a time, so these do not hold together as a set — any growth rate can be made to fit by moving the margin. And it is a statement about the price, not a forecast of the business.",
  },

  "lookback-window": {
    term: "The lookback window",
    what: "The stretch of past trading days every figure on this page was measured over.",
    why: "Weights, expected returns, volatility and the equity curve all come from this window and nothing outside it.",
    careful:
      "It looks backwards, so it is a record and not a forecast. A window that happens to contain one long bull market will make almost any portfolio look good, and a different two years would give different weights from the same method.",
  },
  "screen-yartseva": {
    term: "Yartseva multibagger screen",
    what: "A two-stage screen: hard filters on growth, cash generation and valuation, then a composite score out of 100 for the names that clear them.",
    why: "It is looking for companies early in a long run rather than cheap ones — growth that is already showing up in EBITDA and free cash flow, at a price that has not caught up.",
    careful:
      "Deliberately narrow, so most of the index fails and that is the intended behaviour. Figures come from yfinance quarterly data, which is a proxy for the filings, not the filings.",
  },
  "screen-acquisition": {
    term: "Acquisition compounder screen",
    what: "Hard filters on growth, return on capital, cash conversion, leverage, margins and dilution, then a nine-factor score out of 45.",
    why: "It looks for businesses that grow by buying others and actually earn a return on what they pay — the pattern works rarely and fails expensively, so the filters are strict about leverage and share issuance.",
    careful:
      "Organic growth here is a revenue proxy, not a reported figure, so a company growing purely by acquisition can look organic. Check the segment disclosures before believing the growth split.",
  },
  "screen-bolton": {
    term: "Bolton contrarian screen",
    what: "Anthony Bolton's special-situations framework, automated as far as it honestly goes: cheap on at least one multiple, sitting low in its own 52-week range, and generating enough cash to survive the wait. Scored out of 100 across valuation, neglect, balance sheet, insider buying and whether the fall has stopped.",
    why: "Bolton compounded at around 20% a year for 28 years by buying what the market had given up on. The measurable part of that — cheap, unloved, solvent — is exactly what a screen is good for.",
    careful:
      "This list is not a list of buys, and the gap is the whole point. Bolton's framework has a fifth section — the catalyst — and he says cheap without one is a value trap. Restructurings, spin-offs, hidden assets and legal overhangs lifting cannot be read from a data feed, so the screen does not score them and does not pretend to. Open a name and ask the Bolton persona what changes it; if there is no answer, that is your answer.",
  },
  "screen-universe": {
    term: "Universe",
    what: "The list of companies a screen was run against — by default the S&P 500.",
    why: "A screen is only as broad as its universe: nothing outside it can ever appear, however well it would have scored.",
    careful:
      "Other markets are available but not pre-computed, because each name costs several seconds to fetch and a five-hundred-name run takes minutes. The Dow and NASDAQ-100 loaders are currently broken upstream.",
  },
  "autoresearch-decay": {
    term: "Fitted versus tested",
    what: "Each rule is fitted on an older slice of history, then tested on a more recent slice it never saw. The chart runs from the first to the second.",
    why: "A rule that looks good on the data it was built from has proven nothing — that is what fitting does. The only evidence is what it did on data it had no access to.",
    careful:
      "Leftward movement means the rule was partly fitting noise, and almost all of them move left. The dashed line is buy-and-hold on the same window after fees: a rule landing left of it lost to doing nothing, which is the real bar, not zero.",
  },
  "autoresearch-loop": {
    term: "Auto research",
    what: "A loop that proposes a trading rule, backtests it, tests it on data it has not seen, and keeps it only if it beat buy-and-hold out of sample.",
    why: "Its main output is rejection. Trying a hundred rules and keeping the best one finds noise; a loop that records every attempt and raises the bar as the count grows is the only way a survivor means anything.",
    careful:
      "The bar rises with the number of experiments, because trying more things makes a lucky result more likely. A rule kept after eight attempts is weaker evidence than the same rule kept after two.",
  },
  // ── Play it ────────────────────────────────────────────────────────────
  "position-size": {
    term: "Largest position this justifies",
    what: "The biggest share of your book this level of conviction allows, as a stated policy rather than a formula.",
    why: "Written down and adjustable rather than hidden inside an equation, because it is a judgment about risk, not arithmetic.",
    careful:
      "Deliberately below what a confident reading would allow. An overestimated edge is not merely imprecise — bet the full amount on a drift you have overstated twofold and the long-run growth rate is exactly zero.",
  },
  "implied-conviction": {
    term: "What your book claims",
    what: "Run backwards: for each position you already hold, the conviction that its size is implicitly claiming.",
    why: "The uncomfortable direction, and the useful one. A position is a statement about conviction whether or not anyone wrote the statement down.",
  },
} as const satisfies Record<string, GlossaryEntry>;

export type GlossaryKey = keyof typeof GLOSSARY;

/*
 * PERSONA_NOTES used to live here: a hand-written description of each investor,
 * separate from the prompt that actually governs their verdict. It drifted, and
 * the drift was invisible — the panel explaining how an investor judges could
 * disagree with the instruction the model was given.
 *
 * It now comes from `agents/profiles.py` via GET /research/personas, which is
 * the same object used to build the preamble. See api.ts `InvestorProfile`.
 */
