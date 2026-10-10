"""The criteria fingerprint, and the registry it depends on.

A fingerprint that silently stops covering a threshold is worse than no
fingerprint at all: it keeps asserting "nothing changed" while something did,
which is the exact failure it was built to catch, now wearing a tick.

So the load-bearing test here is not that the hash is stable. It is
`test_every_threshold_constant_is_registered`, which walks each screen module
for module-level threshold constants and fails when one is missing from
`criteria.REGISTRY`. Add a threshold and forget to register it, and this test
names it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from hedge_fund.screeners import cache, criteria

SCREEN_MODULES = {
    "acquisition-compounder": "acquisition_compounder",
    "yartseva": "yartseva",
    "bolton-contrarian": "bolton_contrarian",
    "kiyohara-handbook": "kiyohara_handbook",
    "ellenbogen-two-act": "ellenbogen_two_act",
}

#: Module-level constants that do not change what the screen returns, so they
#: do not belong in the fingerprint. Kept as an explicit allow-list rather than
#: a pattern, so adding one is a decision somebody makes on purpose.
NOT_CRITERIA = {
    # Documentation of what the screen deliberately ignores. Changing the
    # tuple changes the prose, not the arithmetic.
    "IGNORED_BY_DESIGN",
    # The judgments the two-act framework is made of, named so the result can
    # carry them. Changing the tuple changes what the row discloses, not what
    # the arithmetic does.
    "UNCHECKABLE_BY_DESIGN",
    # Column-name candidates and provider plumbing, not thresholds.
    "SHARE_COUNT_ROWS",
    "CASH_ROWS",
    "DEBT_ROWS",
    "EQUITY_ROWS",
    "ASSET_ROWS",
}


def _module_path(mod: str) -> Path:
    return Path(__file__).resolve().parents[1] / "src" / "hedge_fund" / "screeners" / f"{mod}.py"


def _threshold_constants(mod: str) -> set[str]:
    """Module-level UPPER_CASE assignments that look like screen rules.

    Parsed rather than imported so this sees what is written in the file,
    including a constant that is defined and not yet used anywhere.
    """
    tree = ast.parse(_module_path(mod).read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for t in targets:
            if isinstance(t, ast.Name) and re.fullmatch(r"[A-Z][A-Z0-9_]*", t.id):
                if not t.id.startswith("_") and t.id not in NOT_CRITERIA:
                    found.add(t.id)
    return found


@pytest.mark.parametrize("screen,mod", sorted(SCREEN_MODULES.items()))
def test_every_threshold_constant_is_registered(screen: str, mod: str):
    """Every rule the module states must appear in the fingerprint.

    This is the test that keeps `criteria.py` honest. Without it the registry
    is a hand-maintained mirror, and a hand-maintained mirror of thresholds is
    the second place for a number to live — the thing this whole mechanism
    exists to prevent.
    """
    declared = _threshold_constants(mod)
    registered = criteria.criteria_for(screen) or {}

    # Compared case-insensitively on the name: the registry keys are the
    # snake_case spelling of the constant, by convention.
    reg_keys = {k.upper() for k in registered}
    missing = {c for c in declared if c not in reg_keys}

    assert not missing, (
        f"{mod}.py declares {sorted(missing)} but criteria.REGISTRY does not cover "
        f"them. A threshold outside the fingerprint means changing it leaves every "
        f"cached run claiming it is current. Register it in criteria.py, or add it "
        f"to NOT_CRITERIA in this test with a reason."
    )


@pytest.mark.parametrize("screen", sorted(SCREEN_MODULES))
def test_every_cached_screen_has_a_fingerprint(screen: str):
    assert criteria.fingerprint(screen), f"{screen} has no fingerprint"


def test_the_registry_covers_exactly_the_screens_that_have_caches():
    assert set(criteria.REGISTRY) == set(cache.SCREENS), (
        "a screen with a cache but no registered criteria writes a null "
        "fingerprint, so its cache can never be detected as stale"
    )


def test_an_unknown_screen_has_no_fingerprint():
    assert criteria.fingerprint("not-a-screen") is None
    assert criteria.criteria_for("not-a-screen") is None


def test_the_fingerprint_is_stable_across_calls():
    """Same rules, same hash — or every read would report a false change."""
    assert criteria.fingerprint("yartseva") == criteria.fingerprint("yartseva")


def test_the_fingerprint_moves_when_a_threshold_moves(monkeypatch):
    """The whole point. A changed rule must produce a changed hash."""
    from hedge_fund.screeners import acquisition_compounder as ac

    before = criteria.fingerprint("acquisition-compounder")
    monkeypatch.setattr(ac, "MIN_ROIC", ac.MIN_ROIC + 0.01)
    after = criteria.fingerprint("acquisition-compounder")
    assert before != after


def test_the_fingerprint_moves_when_the_cap_band_moves(monkeypatch):
    """Nested structures count too, not just scalars."""
    from hedge_fund.screeners import acquisition_compounder as ac

    before = criteria.fingerprint("acquisition-compounder")
    monkeypatch.setattr(
        ac,
        "CAP_BAND_BY_CURRENCY",
        {**ac.CAP_BAND_BY_CURRENCY, "USD": (1, 2)},
    )
    assert criteria.fingerprint("acquisition-compounder") != before


def _cached(**over):
    base = dict(
        screen="acquisition-compounder",
        universe="sp400",
        built_at="2026-10-09T00:00:00+00:00",
        results=[],
        requested=0,
        errors=0,
        duration_s=1.0,
        criteria=criteria.fingerprint("acquisition-compounder"),
    )
    base.update(over)
    return cache.CachedScreen(**base)


def test_a_matching_cache_is_not_flagged():
    got = _cached()
    assert got.criteria_changed is False
    assert got.as_dict()["criteria_known"] is True


def test_a_cache_built_under_other_rules_is_flagged():
    got = _cached(criteria="deadbeef0000")
    assert got.criteria_changed is True
    d = got.as_dict()
    assert d["criteria_known"] is True
    assert d["criteria"] == "deadbeef0000"
    assert d["criteria_current"] == criteria.fingerprint("acquisition-compounder")


def test_a_cache_from_before_fingerprints_reports_unknown_not_changed():
    """The pre-existing files on disk have no `criteria` key.

    Reporting those as changed would mark every old cache wrong on no
    evidence; reporting them as unchanged would be the original bug. Unknown
    is the only honest answer, so `criteria_known` carries it.
    """
    got = _cached(criteria=None)
    assert got.criteria_changed is False
    assert got.as_dict()["criteria_known"] is False


def test_a_cache_for_an_unregistered_screen_reports_unknown():
    got = _cached(screen="not-a-screen", criteria="abc123")
    assert got.criteria_changed is False
    assert got.as_dict()["criteria_known"] is False
