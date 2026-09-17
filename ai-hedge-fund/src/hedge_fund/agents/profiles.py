"""Who each investor is, and what they actually test.

This exists so the app can answer "how is this being judged?" without the
answer being written twice.

The preamble in `personas.py` is what the model is told. The description the
reader sees used to be a separate hand-written note in the frontend's
`glossary.ts` — a second, independent account of the same investor, in another
language, maintained by hand. Two descriptions of one thing drift, and the
failure is invisible and bad: the screen tells the reader an investor weighs X
while the model has been instructed to weigh Y. The reader then trusts a
verdict on the strength of a description that does not govern it.

So the profile lives here, next to the preamble, and the API serves it. One
edit, one source, and a test asserts that every persona with a prompt has a
profile and vice versa.

`tests` is the part worth the trouble: the concrete checks the investor is
known for, in their own terms, phrased so a reader can hold the verdict up
against them. Keep them specific — "price-to-book under 1.5" is checkable,
"looks for value" is not.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InvestorProfile:
    #: Display name. The UI shows this rather than the id.
    name: str
    #: One line on who they are and why their record is worth borrowing.
    who: str
    #: How they think — the shape of the judgment, in two or three lines.
    style: str
    #: What they concretely check. Specific enough to audit a verdict against.
    tests: tuple[str, ...]
    #: The one sentence that captures the whole approach.
    essence: str


PROFILES: dict[str, InvestorProfile] = {
    "default": InvestorProfile(
        name="House analyst",
        who="No persona — the unstyled, disciplined default.",
        style=(
            "Weighs the evidence in the data bundle without a house preference for growth "
            "or value, and says plainly when the data does not support a view."
        ),
        tests=(
            "Is the claim supported by a number in the bundle?",
            "Is the data fresh enough to rely on?",
            "What would have to be true for this to be wrong?",
        ),
        essence="Follow the evidence, and admit when there isn't any.",
    ),
    "warren_buffett": InvestorProfile(
        name="Warren Buffett",
        who="Berkshire Hathaway. Sixty years of compounding by owning businesses rather than renting stocks.",
        style=(
            "Starts from the business, not the share price: would you want to own all of this "
            "company for a decade? Wants a durable competitive advantage, honest managers who "
            "behave like owners, and a price that leaves room to be wrong. Prefers a wonderful "
            "business at a fair price to a fair business at a wonderful price."
        ),
        tests=(
            "A moat that will still be there in ten years — brand, switching costs, scale, low-cost position",
            "Owner earnings: cash the owner could actually take out, not reported profit",
            "High return on capital without heavy debt",
            "Management candour, and capital allocation that has served shareholders",
            "A business simple enough to understand — inside the circle of competence",
        ),
        essence="Buy a great business at a fair price and let time do the work.",
    ),
    "ben_graham": InvestorProfile(
        name="Ben Graham",
        who="The father of security analysis, and Buffett's teacher.",
        style=(
            "Buys statistical cheapness, not stories. Assumes he will be wrong often, so the "
            "protection has to be in the price and the balance sheet rather than in the "
            "forecast. Treats the market as a manic counterparty to transact against, not an "
            "authority to defer to."
        ),
        tests=(
            "Margin of safety: price far enough below conservative value to absorb error",
            "Net current asset value — ideally buying assets for less than they are worth",
            "Strong current ratio and modest debt",
            "A long earnings record, not one good year",
            "Tangible evidence of cheapness rather than projected growth",
        ),
        essence="Pay so little that you don't need to be right.",
    ),
    "charlie_munger": InvestorProfile(
        name="Charlie Munger",
        who="Buffett's partner at Berkshire for over four decades.",
        style=(
            "Inverts: asks what would make this a disaster and whether that is likely, before "
            "asking what would make it work. Demands quality and simplicity, and would rather "
            "hold a few outstanding businesses than diversify into mediocrity. Deeply "
            "suspicious of complexity used to justify a price."
        ),
        tests=(
            "Invert: what would destroy this business, and how probable is that?",
            "Quality of the business over cheapness of the stock",
            "Incentives — what is management actually paid to do?",
            "Is the thesis simple enough to state in a sentence?",
            "Avoid the obviously stupid rather than seek the brilliant",
        ),
        essence="Avoid the ways to lose, and a few good decisions will carry you.",
    ),
    "anthony_bolton": InvestorProfile(
        name="Anthony Bolton",
        who="Ran Fidelity Special Situations for 28 years at roughly 20% a year — one of the longest winning records in European fund management.",
        style=(
            "Hunts where sentiment has overshot the facts: a company the market has given up "
            "on, where something specific is about to change the story. Works in a strict "
            "order — cheap, then unloved, then a reason to re-rate — and refuses to skip the "
            "third. Cheap without a catalyst he calls a value trap by name."
        ),
        tests=(
            "Cheap on its own history and against peers: low P/E, price-to-book under ~1.5, EV/EBITDA under ~7, price-to-free-cash-flow under ~15",
            "Unloved: near 52-week lows, thin analyst coverage, institutions selling, heavy short interest, or a spin-off dumped by index funds",
            "A catalyst — restructuring, hidden asset, legal overhang lifting, earnings inflection still priced as decline",
            "Able to survive the wait: debt-to-equity under ~1, interest cover above 3x, cash flow ahead of reported profit, insiders buying",
            "The strongest bear argument stated explicitly, and judged overblown or correct",
        ),
        essence="Buy what everyone hates, but only when you can name what changes it.",
    ),
    "norbert_lou": InvestorProfile(
        name="Norbert Lou",
        who="Punch Card Capital. Named for Buffett's idea that a lifetime of investing needs about twenty decisions.",
        style=(
            "Almost everything is a pass, said quickly and without hedging. When he does "
            "engage, he goes far deeper than a screen — one business, understood well enough "
            "to be indifferent to the next three years of quotes, bought when a temporary "
            "problem is being priced as permanent. A thin thesis is a pass, never a small "
            "position."
        ),
        tests=(
            "Does this need to be owned at all? Most answers are no",
            "Understood deeply enough to ignore the share price for years",
            "A temporary problem the market is treating as permanent",
            "Unglamorous and ignored rather than debated",
            "Nothing that would have to be checked weekly",
        ),
        essence="Twenty decisions in a lifetime, so almost everything is a no.",
    ),
    "li_lu": InvestorProfile(
        name="Li Lu",
        who="Himalaya Capital. Introduced Munger to BYD, and ran the only outside money Munger ever allocated.",
        style=(
            "Concentrates in a handful of businesses understood well enough to hold through a "
            "halving. Strong bias to founder-led companies compounding inside a growing "
            "domestic economy. Insists on the franchise and the discount together, and says so "
            "when only one of the two is present."
        ),
        tests=(
            "A durable franchise, not a cyclical upswing",
            "A price that already assumes disappointment",
            "Founder or owner-operator with skin in the game",
            "A business you would hold through a 50% drawdown without selling",
            "Concentration — few enough positions to know each one properly",
        ),
        essence="A few businesses you understand completely, bought when they're doubted.",
    ),
    "mohnish_pabrai": InvestorProfile(
        name="Mohnish Pabrai",
        who="Pabrai Investment Funds. Openly clones the best ideas of better-known investors.",
        style=(
            "Looks for bets where the downside is largely capped and the upside is several "
            "times the stake — 'heads I win, tails I don't lose much'. Few bets, big when the "
            "odds are right, and no bet at all when the asymmetry isn't there. Comfortable "
            "copying a good idea rather than originating one."
        ),
        tests=(
            "Asymmetry: how much can be lost versus how much can be made?",
            "Low risk and high uncertainty — the combination the market misprices",
            "A simple, already-proven business rather than a new one",
            "Few positions, sized to matter",
            "Is there a clear reason the market is wrong right now?",
        ),
        essence="Heads I win, tails I don't lose much — and bet big when it's true.",
    ),
    "michael_burry": InvestorProfile(
        name="Michael Burry",
        who="Scion Capital. Shorted subprime mortgages before the 2008 crisis.",
        style=(
            "Reads the primary documents nobody else reads and takes the other side of a "
            "crowded consensus. Deeply sceptical of accounting, of leverage, and of anything "
            "everyone agrees about. Expects to be early and uncomfortable."
        ),
        tests=(
            "Where is the consensus crowded, and what is it ignoring?",
            "Balance-sheet stress hidden in the footnotes",
            "Accounting that flatters the reported numbers",
            "What does the bear case look like if it is right?",
            "Is the mispricing large enough to survive being early?",
        ),
        essence="Read what nobody reads, then take the other side.",
    ),
    "cathie_wood": InvestorProfile(
        name="Cathie Wood",
        who="ARK Invest. Concentrated, high-conviction bets on technological disruption.",
        style=(
            "Thinks in five-year arcs about technologies whose costs are falling fast enough "
            "to open new markets. Tolerates enormous volatility and current unprofitability "
            "for exposure to exponential adoption. The risk is paying for a narrative the "
            "fundamentals never reach."
        ),
        tests=(
            "A cost curve falling fast enough to create a new market",
            "Total addressable market large enough to justify the multiple",
            "Revenue growth that is actually accelerating",
            "A technology lead that compounds rather than commoditises",
            "Willingness to hold through severe drawdowns",
        ),
        essence="Own the disruption early and accept the volatility that comes with it.",
    ),
    "peter_lynch": InvestorProfile(
        name="Peter Lynch",
        who="Ran Fidelity Magellan to roughly 29% a year over thirteen years.",
        style=(
            "Prefers businesses he can explain in a sentence and check in the real world. "
            "Sorts companies by what kind they are — slow grower, stalwart, fast grower, "
            "cyclical, turnaround, asset play — because each needs a different test. Watches "
            "growth against the multiple paid for it."
        ),
        tests=(
            "Can you explain what the company does in one sentence?",
            "PEG: is the multiple justified by the growth rate?",
            "Which of the six company types is this, and is it judged on the right terms?",
            "Inventory, margins and debt trending the right way",
            "Is the story still intact, or has it quietly changed?",
        ),
        essence="Buy what you can explain, and pay attention to growth versus price.",
    ),
    "phil_fisher": InvestorProfile(
        name="Phil Fisher",
        who="Wrote Common Stocks and Uncommon Profits; the growth half of Buffett's thinking.",
        style=(
            "Judges the organisation, not the quarter: research depth, sales strength, margin "
            "discipline and the quality and integrity of management. Buys few companies and "
            "holds them for very long periods. Gathers evidence from people around the "
            "business — the 'scuttlebutt' method."
        ),
        tests=(
            "Products with enough runway for years of sales growth",
            "Real R&D productivity, not just R&D spending",
            "Above-average profit margins, and a plan to defend them",
            "Management depth and unquestionable integrity",
            "Labour, executive and cost-control quality",
        ),
        essence="Find an exceptional organisation and hold it for a very long time.",
    ),
    "aswath_damodaran": InvestorProfile(
        name="Aswath Damodaran",
        who="NYU valuation professor; the discipline against which stories get checked.",
        style=(
            "Every valuation is a story disciplined by numbers, and the numbers must be "
            "mutually consistent. Attacks the assumptions rather than the conclusion: what "
            "growth, margin and cost of capital does this price require, and are they "
            "plausible together for a company this size in this market?"
        ),
        tests=(
            "What growth and margin does today's price actually imply?",
            "Cost of capital appropriate to the risk, not borrowed from elsewhere",
            "Reinvestment consistent with the growth being claimed",
            "Is the terminal value doing all the work?",
            "Does the narrative match the numbers, and vice versa?",
        ),
        essence="A price is a story; check whether its numbers could both be true.",
    ),
    "bill_ackman": InvestorProfile(
        name="Bill Ackman",
        who="Pershing Square. Concentrated activist positions in large, simple businesses.",
        style=(
            "Takes a few very large positions in predictable, free-cash-generative businesses "
            "and then argues publicly for the change that unlocks value. Thesis-driven and "
            "explicit about what must happen; willing to be loudly wrong in public."
        ),
        tests=(
            "A simple, predictable, free-cash-generative business",
            "A specific change — strategy, management, structure — that would unlock value",
            "Is there a credible path to forcing that change?",
            "Quality of management, and whether they are the obstacle",
            "Position size justified by the clarity of the thesis",
        ),
        essence="Concentrate in a simple business and push for the change that unlocks it.",
    ),
    "stanley_druckenmiller": InvestorProfile(
        name="Stanley Druckenmiller",
        who="Duquesne Capital. Roughly 30% a year for three decades with no losing year.",
        style=(
            "Starts with liquidity and the macro regime, because that decides which "
            "fundamentals matter. Takes very large positions when conviction is high and exits "
            "without ceremony when the thesis breaks. Watches what the market is telling him "
            "more than what he believed last month."
        ),
        tests=(
            "What is central-bank liquidity doing, and who does that favour?",
            "Which regime are we in — and is it changing?",
            "Asymmetry large enough to justify real size",
            "What price action disagrees with the thesis?",
            "Would you still hold this if it moved against you tomorrow?",
        ),
        essence="Get the regime right, size up when you're sure, and leave when you're wrong.",
    ),
    "rakesh_jhunjhunwala": InvestorProfile(
        name="Rakesh Jhunjhunwala",
        who="India's best-known equity investor; compounded a small stake into a fortune over three decades.",
        style=(
            "Backs businesses riding a long domestic growth wave, and holds them through "
            "extreme volatility. Wants the structural tailwind and the business quality to "
            "align with the reported numbers before committing, then is extremely patient."
        ),
        tests=(
            "A structural, multi-decade demand tailwind",
            "Business quality and returns on capital that justify holding",
            "Management with a track record through a full cycle",
            "Valuation reasonable against the growth actually being delivered",
            "Patience: prepared to hold through severe drawdowns",
        ),
        essence="Ride a long structural growth wave, and hold through the noise.",
    ),
}
