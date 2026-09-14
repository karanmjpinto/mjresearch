# Third-party attribution

## virattt / ai-hedge-fund

This project’s **investor persona** and **committee / portfolio-manager synthesis** ideas are inspired by the educational multi-agent design in [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (MIT License).

- Upstream repository: https://github.com/virattt/ai-hedge-fund  
- License: MIT (see upstream `LICENSE`)

The **system prompts** under `src/hedge_fund/agents/personas.py` are **original text** written for this codebase (not copied from upstream source files). They aim to capture publicly discussed investment *styles* associated with named investors for research/education only — not investment advice, and not endorsement by any person or firm.

## Financial Datasets

Optional market data integration uses [Financial Datasets](https://financialdatasets.ai/) HTTP APIs when `FINANCIAL_DATASETS_API_KEY` is set. Refer to their terms of use and pricing.

## Methodology sources

Where a model here follows someone else's published reasoning, this is the list. None of these people have endorsed this code, and any error in applying their work is ours.

### Aswath Damodaran

The cost-of-capital build-up, the three-requisite conviction chain and the conviction-to-concentration argument follow his published framing. The equity risk premium, country risk premiums and rating spreads are his published datasets, committed under `config/damodaran/` with their own `as_of` dates rather than fetched — see `src/hedge_fund/valuation/reference.py` for why.

### Edward O. Thorp — the Kelly criterion

> Thorp, Edward O. "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market." Paper presented at the 10th International Conference on Gambling and Risk Taking, Montreal, June 1997. Revised 29 May 1998.

Read at <https://sites.oxy.edu/lengyel/M330/thorp/paper1.pdf> (a course page at Occidental College; the paper is widely mirrored).

Cited in `src/hedge_fund/valuation/concentration.py`, which takes from it the direction of the position-size adjustment under an uncertain edge, and the precedent for a hard ceiling on top of any sizing rule. It does **not** implement Kelly: the conviction chain yields no per-name drift or variance, so there is no `f*` here to take a fraction of.

**Cite the 1998 revision, not the 1997 conference version.** The title page carries "Montreal, June 1997" with a footnote "Revised May 29, 1998", and the paper discusses 1998 events — so page references taken from this PDF cannot be attributed to the version presented in 1997. Note also that Figures 1–5 and Appendices 2–3 are referenced in the text but absent from this PDF, including the figure underlying the estimation-error section; every passage quoted in this codebase is prose, not read off a missing figure.

**The PDF is not vendored into this repository.** Page 1 carries "©1997" with no licence, no reproduction grant and no public-domain dedication. The only evidence of the author consenting to web distribution is his acknowledgement thanking "Richard Reid for posting this paper on his website" — permission for one posting, not a general grant. This repository is public, so the paper is linked and quoted briefly with page cites, the same way `config/damodaran/` cites a source instead of mirroring the spreadsheets behind it.
