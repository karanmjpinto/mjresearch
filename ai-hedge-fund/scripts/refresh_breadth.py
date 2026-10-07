"""Rebuild the stored breadth series.

Run from the repo root:

    uv run python scripts/refresh_breadth.py                 # S&P 500, from 2004
    uv run python scripts/refresh_breadth.py --start 1999-01-01
    uv run python scripts/refresh_breadth.py --universe sp600

This is the expensive half of the breadth screen: five hundred daily price
histories, about half a minute in one batched yfinance call. It is a single
`download` rather than five hundred, which is why this script is short and the
screens refresher is not — breadth needs only closes, and closes come back for
the whole universe at once.

The default start is 2004 rather than the furthest back yfinance will go. Two
reasons, and the second is the real one:

*   Membership is today's, carried backwards. The further back the window, the
    fewer of today's members had listed, and the more the measure is describing
    a few hundred large survivors rather than an index.
*   Nothing before 2004 makes the signal testable anyway. The divergences the
    warning was built on are in 1929, 1962, 1973 and 1987, and no free
    constituent-level source reaches them. A longer window buys a little more
    sample and a lot more false confidence that the original claim is being
    tested. It is not.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import pandas as pd

from hedge_fund.breadth import from_closes, write
from hedge_fund.data.universes import load_universe

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("breadth")

DEFAULT_START = "2004-01-01"
INDEX_SYMBOL = "^GSPC"


def _closes(symbols: list[str], start: str) -> pd.DataFrame:
    """Adjusted daily closes for a whole universe in one call.

    `auto_adjust=True` is load-bearing here in a way it is not for a single
    price chart: an unadjusted frame turns every 2-for-1 split into a 50%
    decline, and the advance-decline line counts declines.
    """
    import yfinance as yf

    raw = yf.download(
        symbols,
        start=start,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    if raw is None or raw.empty:
        raise SystemExit("the price download came back empty")
    if isinstance(raw.columns, pd.MultiIndex):
        return raw["Close"].sort_index()
    return raw[["Close"]].rename(columns={"Close": symbols[0]}).sort_index()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--universe", default="sp500", help="sp500 (default), sp400, sp600")
    ap.add_argument("--start", default=DEFAULT_START, help="first session, YYYY-MM-DD")
    args = ap.parse_args()

    began = time.time()
    symbols = load_universe(args.universe)
    log.info("%s: %d members", args.universe, len(symbols))

    closes = _closes(symbols, args.start)
    index = _closes([INDEX_SYMBOL], args.start).iloc[:, 0]

    # A member with no column at all is a symbol yfinance did not recognise —
    # usually a recent ticker change. Counting it as a permanent non-advance
    # would drag the A-D line down by a constant, so it is dropped and the
    # count of what was actually fetched is stored beside the series.
    fetched = closes.dropna(axis=1, how="all")
    if fetched.shape[1] < len(symbols):
        log.warning(
            "%d of %d members returned no history and were dropped",
            len(symbols) - fetched.shape[1],
            len(symbols),
        )

    breadth = from_closes(fetched)
    path = write(
        args.universe,
        breadth,
        index,
        index_symbol=INDEX_SYMBOL,
        members_requested=len(symbols),
        members_fetched=int(fetched.shape[1]),
    )

    log.info(
        "wrote %s — %d sessions, %s to %s, %.0fs",
        path,
        len(breadth),
        breadth.dates[0].date(),
        breadth.dates[-1].date(),
        time.time() - began,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
