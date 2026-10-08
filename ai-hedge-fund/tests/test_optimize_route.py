"""The optimiser has to survive providers that disagree about what a date is.

A basket is assembled from whichever provider answered for each name, and they
do not return the same index: yfinance hands back a tz-aware index in the
exchange's zone, OpenBB a naive one, and some paths stamp the market open
rather than midnight. Two of those in one basket used to raise
`Cannot join tz-naive with tz-aware DatetimeIndex` and return a 500 — and the
timestamp half failed worse than that, joining to an empty frame and reading
back as "these tickers never traded together".

The date-flooring itself now lives in `hedge_fund.data.frames`, shared with the
other price consumers, and `tests/test_data_frames.py` covers it directly. What
stays here is the route: a basket of three differently-stamped providers has to
come out with all three names in it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from hedge_fund.api.routes import optimize as route


def _prices(n: int = 120, *, tz: str | None = None, hour: int = 0, seed: int = 0):
    idx = pd.date_range("2024-01-01", periods=n, freq="B", tz=tz)
    if hour:
        idx = idx + pd.Timedelta(hours=hour)
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"close": 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, n))}, index=idx)


def test_mixed_timezone_basket_optimises(monkeypatch):
    frames = {
        "AAA": _prices(tz="US/Eastern", hour=9, seed=1),
        "BBB": _prices(seed=2),
        "CCC": _prices(tz="UTC", seed=3),
    }
    monkeypatch.setattr(
        route._ds, "get_price_history", lambda t, days=730: frames[t], raising=False
    )

    out = route.optimize(route.OptimizeRequest(tickers=list(frames), method="hrp"))

    # Every name survived the join — the bug dropped the whole request.
    assert {a["ticker"] for a in out["assets"]} == set(frames)
    assert out["n_bars"] > 100
    assert out["excluded_tickers"] == []
    # The window is what the new timeline draws, so it has to be a real date.
    assert out["start_date"] == "2024-01-01"
    assert abs(sum(a["weight"] for a in out["assets"]) - 1.0) < 1e-6
