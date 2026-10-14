"""The screener API's registries, and the two places they can silently drift.

Both checks here are derived from `cache.SCREENS` rather than hand-written,
because a hand-written list of screens is the thing that goes stale — the
currency-band test in the compounder suite spent two releases claiming to
cover "the eight shipped universes" while naming six currencies.
"""

from __future__ import annotations


def test_every_screen_has_a_background_runner():
    """The refresh button is only as complete as this dict.

    Four of the six screens had no entry here, so the UI could offer a
    refresh for a screen the API had no way to run — a button that returns
    404 and reads as a broken feature rather than an unimplemented one.
    Derived from `cache.SCREENS` so adding a screen fails here rather than
    in someone's hands.
    """
    from hedge_fund.api.routes.screeners import _RUNNERS
    from hedge_fund.screeners.cache import SCREENS

    missing = sorted(set(SCREENS) - set(_RUNNERS))
    assert not missing, f"screens with no background runner: {missing}"


def test_run_level_finalisers_match_the_refresh_script():
    """The button and the script must write the same cache.

    `ai-rollup` needs a pass over the finished run to count in-band industry
    peers. That hook is registered twice — once for the API, once for the
    CLI — and if the two drift, the same screen gets a fragmentation column
    through one path and an empty one through the other, with no error
    either way.
    """
    from hedge_fund.api.routes.screeners import _FINALISERS

    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "_refresh", Path(__file__).resolve().parents[1] / "scripts" / "refresh_screens.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert set(_FINALISERS) == set(mod.FINALISERS), (
        "the API and the refresh script disagree about which screens need a "
        f"run-level pass: api={sorted(_FINALISERS)} script={sorted(mod.FINALISERS)}"
    )
