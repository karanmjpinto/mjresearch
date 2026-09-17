"""The provider probe, and the three-way verdict it returns.

This exists because of a real run: 68 of 503 names came back rate-limited
partway through a screen refresh, and the screen was written anyway — a
complete-looking cache with an eighth of it missing. The failure was
environmental and would have been detectable in three seconds, but nothing
asked before committing to twenty minutes of work.

The three-way split is the load-bearing part, and it is borrowed from the
Studio framework's four-status vocabulary. `offline` means the environment
failed and there is nothing to debug in the screen; `failed` would mean the
screen did. Collapsing them produces an alarm nobody reads.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import refresh_screens as rs  # noqa: E402

SCREEN = "bolton-contrarian"


@pytest.fixture
def runners(monkeypatch):
    """Swap the real screen for a scripted one, so no network is touched."""

    def install(fn):
        monkeypatch.setitem(rs.RUNNERS, SCREEN, fn)

    return install


def test_all_probes_clean_is_ok(runners):
    runners(lambda t: {"ticker": t, "passed": True})
    assert rs.preflight(SCREEN) == "ok"


def test_every_probe_refused_is_offline(runners):
    """The environment is down. Do not start, and do not overwrite a cache."""
    runners(lambda t: {"ticker": t, "error": "Too Many Requests. Rate limited."})
    assert rs.preflight(SCREEN) == "offline"


def test_a_raising_provider_is_also_offline(runners):
    """A thrown exception and a returned error are the same situation."""

    def boom(_t):
        raise ConnectionError("connection refused")

    runners(boom)
    assert rs.preflight(SCREEN) == "offline"


def test_partial_success_is_degraded_not_offline(runners):
    """One name failing is a gap to fill, not a reason to abandon the run.

    This is the case the old code got wrong in the other direction: it treated
    a partly-answering provider as fully healthy and wrote the screen.
    """
    seen: list[str] = []

    def flaky(t):
        seen.append(t)
        return (
            {"ticker": t, "error": "rate limited"}
            if t == rs.PREFLIGHT_TICKERS[0]
            else {"ticker": t, "passed": True}
        )

    runners(flaky)
    assert rs.preflight(SCREEN) == "degraded"
    assert len(seen) == len(rs.PREFLIGHT_TICKERS), "every probe should be attempted"


def test_the_probe_is_cheap(runners):
    """Three names. A probe that costs real time is one you will switch off."""
    assert 1 <= len(rs.PREFLIGHT_TICKERS) <= 5
    calls = []
    runners(lambda t: (calls.append(t), {"ticker": t, "passed": True})[1])
    rs.preflight(SCREEN)
    assert len(calls) == len(rs.PREFLIGHT_TICKERS)


def test_the_probe_can_be_skipped_from_the_command_line():
    """An escape hatch has to exist, and has to be explicit."""
    ap = rs.build_parser() if hasattr(rs, "build_parser") else None
    if ap is None:
        # The flag is defined inline in main(); assert on the source instead so
        # the test still fails if the escape hatch is removed.
        src = (Path(rs.__file__)).read_text(encoding="utf-8")
        assert "--no-preflight" in src
    else:  # pragma: no cover - only if the parser is ever extracted
        assert ap.parse_args(["--no-preflight"]).no_preflight is True
