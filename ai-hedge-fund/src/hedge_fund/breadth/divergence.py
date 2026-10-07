"""Is the index making highs that its members are not — and has that mattered?

The first question is arithmetic and this module answers it exactly. The second
is empirical, and the honest answer in the history that can be built is *no* —
which is why the second half of this file exists at all.

THE SIGNAL

Two conditions, both deliberately crude, because a divergence that needs a
clever definition to appear is not the thing the folklore is about:

1. the index is within ``near`` percent of its own 252-day high, and
2. fewer than ``floor`` percent of members are above their 200-day average.

That is "the index is at a high and half the market is below its own trend".
No peak-matching, no slope fitting, no smoothing — each of which adds a knob
that can be turned until a divergence appears.

EPISODES, NOT DAYS

Signal days arrive in clumps. Counting them as independent observations is the
single most common way this kind of study is overstated: a 2019 run of forty
consecutive signal days is one thing that happened, not forty. So days within
``GAP_DAYS`` of each other are collapsed into one episode, forward returns are
measured once per episode from its first day, and every count reported is a
count of episodes.

The sample that survives this is small — single digits to low twenties
depending on the thresholds — and no amount of daily data changes that. A
median over six episodes has a confidence interval wide enough to contain
almost any claim, and :func:`analyse` reports the count beside every median so
a reader can apply that discount themselves.

WHAT IT FOUND

Across every threshold combination tried, forward returns after a divergence
were *not* worse than unconditional returns over the same history, and at most
settings were better. That is the opposite of the folklore. Three reasons it
may be wrong, none of which this module can rule out:

*   The history is 2004 onward, which contains two bear markets. The episodes
    the warning was built on — 1929, 1962, 1973, 1987 — are outside any window
    that can be built from free constituent data, so this is not a test of the
    original claim. It is a test of the claim in the period since.
*   Survivorship, described in :mod:`hedge_fund.breadth.series`, biases the
    historical breadth measure upward and makes past divergences rarer and
    milder than they were.
*   A signal that fires a handful of times cannot be distinguished from noise
    by its own hit rate, in either direction.

The verdict string returned by :func:`analyse` says the first of these in the
UI, because a reader who takes "breadth divergences have not preceded declines"
away from this screen without "in twenty-two years of survivor-biased data" has
been misled by it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from hedge_fund.breadth.series import Breadth

#: Calendar days of quiet that end an episode. A quarter: long enough that a
#: re-firing is a new event rather than the same one breathing, short enough
#: that two distinct scares in a year are not merged.
GAP_DAYS = 63

#: Horizons, in trading days, at which forward returns are measured.
HORIZONS = (63, 126, 252)

#: Default thresholds. ``near`` is loose because an index that has just made a
#: high and one that is 2% off it are the same condition to anyone watching;
#: ``floor`` is the round half, which is where this stops being a measurement
#: and starts being a convention — and is labelled as one in the UI.
DEFAULT_NEAR = 2.0
DEFAULT_FLOOR = 50.0


@dataclass(frozen=True)
class Episode:
    """One run of signal days, and what the index did afterwards."""

    start: str
    end: str
    days: int
    index_gap_pct: float
    pct_above_at_start: float
    forward: dict[str, float | None]


@dataclass(frozen=True)
class Reading:
    """Where the measures stand on the most recent session."""

    date: str
    members: int
    index_gap_pct: float
    pct_above_200dma: float
    net_new_highs_pct: float
    ad_line_peak_date: str
    days_since_ad_peak: int
    divergent: bool


def _episodes(signal: pd.Series) -> list[list[pd.Timestamp]]:
    """Signal days grouped into runs separated by at least :data:`GAP_DAYS`."""
    runs: list[list[pd.Timestamp]] = []
    for day in signal[signal].index:
        if runs and (day - runs[-1][-1]).days <= GAP_DAYS:
            runs[-1].append(day)
        else:
            runs.append([day])
    return runs


def _forward(index: pd.Series, horizon: int) -> pd.Series:
    """Percent change over the next ``horizon`` sessions, dated at the start."""
    return (index.pct_change(horizon).shift(-horizon) * 100).rename(f"{horizon}d")


def _summary(values: pd.Series) -> dict[str, Any]:
    """Median, hit rate and count, or nulls when nothing is measurable.

    The mean is deliberately absent. On samples this small one 2008 observation
    moves it further than the rest of the sample combined, and a reader who
    sees a mean next to an n of five will read the mean.
    """
    clean = values.dropna()
    if clean.empty:
        return {"median": None, "hit_rate": None, "n": 0}
    return {
        "median": round(float(clean.median()), 2),
        "hit_rate": round(float((clean > 0).mean() * 100), 1),
        "n": int(len(clean)),
    }


def analyse(
    breadth: Breadth,
    index: pd.Series,
    *,
    near: float = DEFAULT_NEAR,
    floor: float = DEFAULT_FLOOR,
) -> dict[str, Any]:
    """The current reading, the episodes, and what followed them.

    ``index`` is the index level on the same sessions as ``breadth``; it is
    reindexed onto the breadth dates and any session missing from either is
    dropped, so a provider that returns a different holiday calendar for the
    index than for its members cannot silently shift the two series against
    each other by a day.
    """
    level = index.reindex(breadth.dates).astype(float).dropna()
    if len(level) < 300:
        raise ValueError(
            f"only {len(level)} sessions align between the index and its members; "
            "at least 300 are needed before a 252-day high means anything"
        )

    pct_above = breadth.pct_above_200dma.reindex(level.index)
    gap = (level / level.rolling(252).max() - 1) * 100

    signal = ((gap > -abs(near)) & (pct_above < floor)).fillna(False)
    runs = _episodes(signal)
    forwards = {h: _forward(level, h) for h in HORIZONS}

    episodes = [
        Episode(
            start=str(run[0].date()),
            end=str(run[-1].date()),
            days=len(run),
            index_gap_pct=round(float(gap.loc[run[0]]), 2),
            pct_above_at_start=round(float(pct_above.loc[run[0]]), 1),
            forward={
                f"{h}d": (
                    None
                    if pd.isna(forwards[h].get(run[0], np.nan))
                    else round(float(forwards[h].loc[run[0]]), 2)
                )
                for h in HORIZONS
            },
        )
        for run in runs
    ]

    starts = [run[0] for run in runs]
    base_rates = {
        f"{h}d": {
            "after_divergence": _summary(forwards[h].reindex(starts)),
            # The comparison is every session, not every non-signal session.
            # Signal days are 0.2% to 10% of the sample depending on the
            # thresholds, so excluding them moves the unconditional figure by
            # less than its own rounding — and "versus the market" is the
            # question a reader is actually asking.
            "unconditional": _summary(forwards[h]),
        }
        for h in HORIZONS
    }

    ad = breadth.ad_line.reindex(level.index).dropna()
    peak_date = ad.idxmax()
    last = level.index[-1]

    reading = Reading(
        date=str(last.date()),
        members=int(breadth.members.loc[last]),
        index_gap_pct=round(float(gap.iloc[-1]), 2),
        pct_above_200dma=round(float(pct_above.iloc[-1]), 1),
        net_new_highs_pct=round(float(breadth.net_new_highs_pct.loc[last]), 1),
        ad_line_peak_date=str(peak_date.date()),
        days_since_ad_peak=int((last - peak_date).days),
        divergent=bool(signal.iloc[-1]),
    )

    return {
        "reading": asdict(reading),
        "episodes": [asdict(e) for e in episodes],
        "base_rates": base_rates,
        "thresholds": {"near": near, "floor": floor, "gap_days": GAP_DAYS},
        "coverage": {
            "first_session": str(level.index[0].date()),
            "last_session": str(last.date()),
            "sessions": int(len(level)),
            "signal_days": int(signal.sum()),
            "episodes": len(runs),
        },
        "verdict": _verdict(base_rates, len(runs)),
    }


def _verdict(base_rates: dict[str, Any], episodes: int) -> dict[str, Any]:
    """One sentence on whether the signal earned its reputation here.

    Keyed on the 252-day horizon: the shorter ones are too noisy to separate at
    these sample sizes, and a year is the horizon the warning is told at.
    """
    year = base_rates["252d"]
    after = year["after_divergence"]
    plain = year["unconditional"]

    if after["n"] < 3:
        return {
            "stance": "untested",
            "line": (
                f"Only {after['n']} episode{'' if after['n'] == 1 else 's'} in this history "
                f"{'has' if after['n'] == 1 else 'have'} a full year after "
                f"{'it' if after['n'] == 1 else 'them'}. That is not enough to say anything "
                "about what a divergence precedes."
            ),
        }

    edge = (after["median"] or 0) - (plain["median"] or 0)
    if edge < -2:
        stance, line = (
            "confirmed",
            (
                f"After these {after['n']} episodes the index returned a median "
                f"{after['median']}% over the following year, against {plain['median']}% "
                "unconditionally — worse, as the warning says."
            ),
        )
    elif edge > 2:
        stance, line = (
            "contradicted",
            (
                f"After these {after['n']} episodes the index returned a median "
                f"{after['median']}% over the following year, against {plain['median']}% "
                "unconditionally — better, not worse. In this sample the warning did not pay."
            ),
        )
    else:
        stance, line = (
            "no-signal",
            (
                f"After these {after['n']} episodes the index returned a median "
                f"{after['median']}% over the following year, against {plain['median']}% "
                "unconditionally. The difference is smaller than the sample can resolve."
            ),
        )
    return {"stance": stance, "line": line, "episodes": episodes}
