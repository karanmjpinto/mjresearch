"""The macro map: the arithmetic, the guards, and the committed file.

Two kinds of test here. The statistical ones use planted series where the
answer is known by construction — a series built to move with inflation news
must come back with a positive inflation sensitivity and a growth sensitivity
near zero, and if it does not, the partial correlation is wrong in a way no
amount of staring at real data would reveal. The rest guard the boundaries
that produce confident-looking nonsense: too short a history, a series that
drifts off the quarter grid, a window with a month missing.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from hedge_fund.macro import news, sensitivity


@pytest.fixture(scope="module")
def committed() -> dict:
    try:
        return news.load()
    except news.MacroDataMissing:
        pytest.skip("data/macro/us-macro-news.json not built")


# ── the committed file ────────────────────────────────────────────────────


def test_file_is_aligned(committed: dict) -> None:
    """Every series covers exactly the quarters the news metrics do."""
    n = len(committed["quarters"])
    assert n > 200, "half a century of quarters should be there"
    for axis in ("inflation", "growth"):
        assert len(committed[axis]["news"]) == n
        assert len(committed[axis]["change"]) == n
        assert len(committed[axis]["surprise"]) == n
    for series in committed["series"]:
        assert len(series["returns"]) == n, series["id"]


def test_news_is_standardised(committed: dict) -> None:
    """A sensitivity only reads as a correlation if the metric is standardised."""
    for axis in ("inflation", "growth"):
        values = np.array(committed[axis]["news"], dtype=float)
        # Restandardised over the full history, then trimmed to 1972, so the
        # window here is close to but not exactly mean 0 / sd 1.
        assert abs(float(values.mean())) < 0.2
        assert 0.8 < float(values.std()) < 1.2


def test_news_metrics_are_nearly_independent(committed: dict) -> None:
    """Growth and inflation news must not be the same series twice.

    They are allowed to be related — stagflation exists — but a correlation
    anywhere near ±1 would make the partial correlations unstable and the two
    axes redundant.
    """
    i = np.array(committed["inflation"]["news"], dtype=float)
    g = np.array(committed["growth"]["news"], dtype=float)
    assert abs(float(np.corrcoef(i, g)[0, 1])) < 0.5


def test_the_seventies_and_2022_are_the_inflation_peaks(committed: dict) -> None:
    """A sanity check against history rather than against our own arithmetic.

    If the metric does not put its highest readings in the mid-1970s and 2022,
    something upstream is misaligned by a lag and every point on the map is
    drawn against the wrong quarters.
    """
    quarters = committed["quarters"]
    values = committed["inflation"]["news"]
    top = {quarters[i][:4] for i in np.argsort(values)[-6:]}
    assert top & {"1973", "1974", "1975"}, top
    assert "2022" in top, top


# ── the statistic ─────────────────────────────────────────────────────────


def _grid_length() -> int:
    return len(news.quarters())


def test_a_planted_inflation_series_reads_as_one(committed: dict) -> None:
    infl = np.array(news.metric("inflation"), dtype=float)
    grow = np.array(news.metric("growth"), dtype=float)
    rng = np.random.default_rng(0)
    planted = 0.05 * infl + 0.01 * rng.standard_normal(infl.size)

    got = sensitivity.sensitivity(list(planted))
    assert got["inflation"] > 0.9
    assert abs(got["growth"]) < 0.3
    assert got["quadrant"] in ("overheating", "stagflation")
    # The control matters: a series built only on inflation must not inherit
    # growth sensitivity through the correlation between the two metrics.
    assert abs(got["growth"]) < abs(float(np.corrcoef(planted, grow)[0, 1])) + 0.1


def test_partial_removes_the_control() -> None:
    """A series that is purely the growth metric has no inflation left in it."""
    assert sensitivity._partial(0.5, 0.5, 1.0) == 0.0  # degenerate, guarded to 0
    # x correlates with y only through z: partial goes to zero.
    assert abs(sensitivity._partial(0.36, 0.6, 0.6)) < 1e-9


def test_uncertainty_counts_independent_years_not_quarters() -> None:
    years, error = sensitivity._uncertainty(216)
    assert years == 54.0
    assert 0.13 < error < 0.15
    # The quarter count would halve the error bar for free.
    assert error > 1 / math.sqrt(216 - 3)


def test_quadrants_are_named_by_sign() -> None:
    assert sensitivity.quadrant(-0.2, 0.4) == "goldilocks"
    assert sensitivity.quadrant(0.3, 0.2) == "overheating"
    assert sensitivity.quadrant(-0.4, -0.2) == "recession"
    assert sensitivity.quadrant(0.5, -0.1) == "stagflation"


def test_a_short_series_is_refused_not_estimated(committed: dict) -> None:
    short: list[float | None] = [None] * _grid_length()
    for i in range(news.MIN_QUARTERS - 1):
        short[i] = 0.01 * (i % 7)
    with pytest.raises(sensitivity.NotEnoughHistory):
        sensitivity.sensitivity(short)


def test_a_wrong_length_series_is_an_error() -> None:
    with pytest.raises(ValueError, match="quarters"):
        sensitivity.sensitivity([0.0, 0.1])


# ── aligning monthly data to the grid ─────────────────────────────────────


def test_from_monthly_compounds_the_right_twelve_months(committed: dict) -> None:
    quarters = news.quarters()
    first = quarters[0]
    year, q = first.split("Q")
    end_month = 3 * int(q)
    months = [f"{int(year) - 1:04d}-{m:02d}" for m in range(end_month + 1, 13)]
    months += [f"{year}-{m:02d}" for m in range(1, end_month + 1)]
    assert len(months) == 12

    got = sensitivity.from_monthly(months, [0.01] * 12)
    assert got[0] == pytest.approx(1.01**12 - 1, rel=1e-9)
    assert got[1] is None, "the next quarter has only nine of its twelve months"


def test_a_month_missing_makes_the_window_none(committed: dict) -> None:
    quarters = news.quarters()
    year, q = quarters[0].split("Q")
    end_month = 3 * int(q)
    months = [f"{int(year) - 1:04d}-{m:02d}" for m in range(end_month + 1, 13)]
    months += [f"{year}-{m:02d}" for m in range(1, end_month + 1)]
    values: list[float | None] = [0.01] * 12
    values[4] = None
    assert sensitivity.from_monthly(months, values)[0] is None


def test_from_monthly_matches_labels_not_positions(committed: dict) -> None:
    """A series that starts late must land on its own quarters, not slide left."""
    quarters = news.quarters()
    late = quarters[40]
    year, q = late.split("Q")
    end_month = 3 * int(q)
    months = [f"{int(year) - 1:04d}-{m:02d}" for m in range(end_month + 1, 13)]
    months += [f"{year}-{m:02d}" for m in range(1, end_month + 1)]

    got = sensitivity.from_monthly(months, [0.005] * 12)
    assert got[40] == pytest.approx(1.005**12 - 1, rel=1e-9)
    assert all(v is None for v in got[:40])


# ── the points ────────────────────────────────────────────────────────────


def test_reference_points_reproduce_the_published_signs(committed: dict) -> None:
    """The two points AQR publish that we can check ourselves.

    Equities sit in Goldilocks — paid for growth, hurt by inflation — and
    Treasuries sit in Recession, hurt by both. Their Exhibit 4 puts US equity
    near (-0.22, +0.44) and 10-year Treasuries near (-0.45, -0.19). We are not
    testing the second decimal, which our different proxies cannot match; we
    are testing that the map has not silently flipped an axis or a sign.
    """
    points = {p["id"]: p for p in sensitivity.reference_points()}
    equity = points["us_equity"]
    assert equity["quadrant"] == "goldilocks"
    assert equity["growth"] > 0.25
    assert equity["inflation"] < -0.1

    treasury = points["us_treasury_10y"]
    assert treasury["quadrant"] == "recession"
    assert treasury["inflation"] < -0.25

    energy = next(p for p in points.values() if p["label"] == "Energy")
    assert energy["inflation"] > 0.2, "an oil industry that dislikes inflation is a bug"


def test_every_point_carries_its_own_uncertainty(committed: dict) -> None:
    for point in sensitivity.reference_points():
        assert point["standard_error"] > 0.05, point["label"]
        assert point["independent_years"] == pytest.approx(
            point["quarters"] / news.OVERLAP, rel=1e-6
        )
        assert -1.0 <= point["inflation"] <= 1.0
        assert -1.0 <= point["growth"] <= 1.0


def test_factor_themes_land_on_the_map(committed: dict) -> None:
    points = sensitivity.factor_points()
    if not points:
        pytest.skip("JKP factor file not built")
    assert len(points) >= 10
    assert all(p["kind"] == "factor" for p in points)
    # The claim the tab makes: long-short themes have far less macro exposure
    # than the market does. Stated as a test so it fails if it stops being true.
    market = next(p for p in sensitivity.reference_points() if p["id"] == "us_equity")
    worst = max(abs(p["growth"]) for p in points)
    assert worst < abs(market["growth"])
