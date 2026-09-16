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

/**
 * The investor styles, and who they belong to.
 *
 * Separate from the glossary because these are keyed by the backend's persona
 * ids and are looked up dynamically, not referenced by name in the source.
 *
 * Written as what the style *looks for*, because that is what changes the
 * verdict. "Value investor" is a label; "wants to pay less than the assets are
 * worth and distrusts forecasts" tells you why this one said sell.
 */
export const PERSONA_NOTES: Record<string, { who: string; looks: string }> = {
  warren_buffett: {
    who: "Berkshire Hathaway. Built the best long-run record in public markets by buying whole businesses and holding them.",
    looks:
      "A durable advantage he can describe in a sentence, honest management, and a price that leaves room to be wrong. Passes on anything he cannot explain.",
  },
  ben_graham: {
    who: "The founder of security analysis, and Buffett's teacher.",
    looks:
      "Assets on the balance sheet worth more than the price. Distrusts forecasts entirely and wants a margin of safety in numbers that already exist.",
  },
  charlie_munger: {
    who: "Buffett's partner for four decades.",
    looks:
      "Quality over cheapness — a great business at a fair price rather than the reverse — and the incentives facing the people running it.",
  },
  cathie_wood: {
    who: "ARK Invest. Concentrated bets on technology platforms.",
    looks:
      "A market that could be far larger than it is today, and a cost curve falling fast enough to create one. Tolerates a high price for that.",
  },
  michael_burry: {
    who: "Scion Capital. Best known for being early and alone on the 2008 housing short.",
    looks:
      "What everyone else has stopped checking. Reads the filings for the thing that breaks the consensus, and is comfortable being the only seller.",
  },
  bill_ackman: {
    who: "Pershing Square. Concentrated activist positions.",
    looks:
      "A good business being run badly, where a change he can push for closes the gap. Few names, held loudly.",
  },
  peter_lynch: {
    who: "Ran Fidelity Magellan through its best years.",
    looks:
      "Growth you can see in ordinary life, at a price that has not caught up to it. Compares the growth rate directly against the multiple.",
  },
  phil_fisher: {
    who: "Wrote Common Stocks and Uncommon Profits; the growth half of Buffett's thinking.",
    looks:
      "Research depth, sales organisation, and management that keeps reinvesting well. Willing to hold for decades.",
  },
  mohnish_pabrai: {
    who: "Pabrai Funds. Openly copies Buffett's method.",
    looks:
      "Few bets, big bets, infrequent bets — low downside first, and a business simple enough that little can go wrong.",
  },
  stanley_druckenmiller: {
    who: "Duquesne. Decades without a losing year.",
    looks:
      "Where the macro cycle and liquidity are heading, then the companies geared to it. Changes his mind fast and sizes hard when convinced.",
  },
  rakesh_jhunjhunwala: {
    who: "The best-known investor in Indian public markets.",
    looks:
      "Long-run domestic growth compounding through founder-led businesses, held through volatility others will not sit through.",
  },
  aswath_damodaran: {
    who: "NYU valuation professor, whose published data this app's cost of capital is built from.",
    looks:
      "A story that survives being turned into numbers. Insists the narrative and the spreadsheet be the same argument.",
  },
  default: {
    who: "No house style — a plain read of the same data.",
    looks:
      "The figures on their own terms, without a school of thought pushing the conclusion.",
  },
};
