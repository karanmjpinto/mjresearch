"""Breadth: how many stocks are going up, as opposed to how much the index is.

An index is a weighted average, and a weighted average can rise while most of
its members fall. *Breadth* is the count rather than the average, and the gap
between the two is the oldest warning in technical analysis — the market
"narrowing" ahead of a decline.

Three measures are built here, not one, because the interesting question is
never what a single line did. It is whether the measures agree:

``ad_line``
    The cumulative advance-decline line: each day, members that closed up
    minus members that closed down, summed forward. Scale is meaningless —
    only its shape against the index is read.
``pct_above_200dma``
    Share of members trading above their own 200-day average. Unlike the A-D
    line this is bounded and needs no rebasing, so it is the one the signal in
    :mod:`hedge_fund.breadth.divergence` actually keys on.
``net_new_highs_pct``
    New 52-week highs minus new 52-week lows, as a share of members. The
    fastest of the three to turn, and the noisiest.

WHY THIS IS NOT THE NYSE ADVANCE-DECLINE LINE

The famous series — the one that diverged before 1929, 1962, 1973 and 1987 —
counts *every issue traded on the NYSE*. That includes closed-end funds, rights,
warrants, and six classes of preferred stock, which between them have at times
been over half the issues on the tape and are mostly interest-rate instruments
wearing equity clothing. It is not a worse series than this one; it is a
different series, and it answers a question about the tape rather than about
the five hundred companies in the index.

This module counts the S&P 500. The limit that matters more is in
:func:`from_closes`: membership is *today's*, carried backwards.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

#: Trading days in the moving average behind ``pct_above_200dma``. The round
#: number everyone quotes, kept because the point of this measure is that it is
#: the one other people are also looking at.
MA_WINDOW = 200

#: Trading days in a "52-week" high. 252, not 365: the window is counted in
#: sessions, so a calendar year of holidays does not shorten it.
HIGH_WINDOW = 252

#: Below this many members with a usable close, a day is dropped rather than
#: reported. Early history thins out as members' listings begin, and a
#: percentage computed across forty survivors is not the same statistic as one
#: computed across five hundred — it is a different, much noisier series that
#: would be plotted on the same axis as if it were comparable.
MIN_MEMBERS = 200


@dataclass(frozen=True)
class Breadth:
    """The three measures on a shared date index, plus the member count.

    ``members`` is carried rather than discarded because it is the honesty of
    every other column: a reader who can see the count fall to 210 in 2004 can
    see for themselves which end of the chart to trust.
    """

    dates: pd.DatetimeIndex
    ad_line: pd.Series
    pct_above_200dma: pd.Series
    net_new_highs_pct: pd.Series
    members: pd.Series

    def __len__(self) -> int:
        return len(self.dates)


def from_closes(closes: pd.DataFrame) -> Breadth:
    """Build the three measures from a frame of adjusted closes.

    One column per member, one row per session, NaN where a member had not yet
    listed. Adjusted closes are assumed: on an unadjusted frame a split shows
    up as a decline, and a day with twelve splits is twelve false declines.

    SURVIVORSHIP, WHICH IS NOT A FOOTNOTE

    The caller passes *current* index members. Every company that was in the
    S&P 500 in 2008 and is not in it now — Lehman, Bear, Wachovia, GM, Circuit
    City — is absent, and they are absent precisely because they fell. So the
    historical A-D line built here is biased upward, and the bias is largest
    exactly where it does most damage: in the declines the series exists to
    warn about.

    The practical consequence is that the divergence signal *under-fires* in
    history. Episodes it finds in the past are the survivors' version of the
    past; episodes it finds today are measured against today's full membership
    and are real. Comparing the two is the known weak joint in this module,
    and :mod:`hedge_fund.breadth.divergence` reports it rather than netting it
    out, because there is no honest way to net it out without a point-in-time
    membership history this project does not have.
    """
    if closes.empty or closes.shape[1] == 0:
        raise ValueError("no member closes to build breadth from")

    frame = closes.sort_index()
    usable = frame.notna()
    members = usable.sum(axis=1)

    change = frame.diff()
    advances = (change > 0).sum(axis=1)
    declines = (change < 0).sum(axis=1)
    # Unchanged closes are counted in neither, which is the convention: a flat
    # day is not half an advance.
    ad_line = (advances - declines).cumsum()

    above = (frame > frame.rolling(MA_WINDOW).mean()).sum(axis=1)
    pct_above = above / members * 100

    rolling_high = frame.rolling(HIGH_WINDOW).max()
    rolling_low = frame.rolling(HIGH_WINDOW).min()
    new_highs = (frame >= rolling_high).sum(axis=1)
    new_lows = (frame <= rolling_low).sum(axis=1)
    net_hl = (new_highs - new_lows) / members * 100

    thin = members < MIN_MEMBERS
    # The A-D line is cumulative, so dropping thin days leaves a line whose
    # level encodes sessions that are no longer shown. It is rebased on the
    # first kept day for exactly that reason — the level is not a quantity, and
    # treating it as one is how a chart ends up with a meaningless y-axis.
    keep = ~thin
    if not keep.any():
        raise ValueError(
            f"no session has {MIN_MEMBERS} members with a usable close; "
            "the universe or the history is too thin to measure breadth on"
        )

    ad = ad_line[keep]
    ad = ad - ad.iloc[0]

    return Breadth(
        dates=pd.DatetimeIndex(frame.index[keep]),
        ad_line=ad,
        pct_above_200dma=pct_above[keep],
        net_new_highs_pct=net_hl[keep],
        members=members[keep],
    )
