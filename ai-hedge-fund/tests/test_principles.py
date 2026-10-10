"""The desk's principles, and the ones it is honest about not enforcing.

Two failure modes are being guarded here, and the second is the subtle one.

The first is ordinary: an exclusion that does not match the labels real data
actually carries. A principle that silently matches nothing is worse than no
principle, because the screen reports a clean run.

The second is the one this registry exists for. A principle registered as
enforced when nothing enforces it is a lie told in a machine-readable format.
`developed-markets-only` is the live example: it is true of this desk today
purely because of which universes happen to exist, so it is registered as a
judgment with "NOT ENFORCED" stated outright. The test below holds that line.
"""

from __future__ import annotations

import pytest

from hedge_fund.screeners import criteria, principles
from hedge_fund.screeners.principles import excluded_by


class TestExclusionsMatchRealLabels:
    """Matched against the sector/industry strings providers actually emit."""

    @pytest.mark.parametrize(
        "sector,industry,expected",
        [
            ("Consumer Defensive", "Tobacco", "vice"),
            ("Consumer Cyclical", "Resorts & Casinos", "vice"),
            ("Consumer Cyclical", "Gambling", "vice"),
            ("Industrials", "Aerospace & Defense", "defence"),
            ("Energy", "Oil & Gas E&P", "fossil-extraction"),
            ("Energy", "Oil & Gas Drilling", "fossil-extraction"),
            ("Energy", "Thermal Coal", "fossil-extraction"),
        ],
    )
    def test_excluded_industries_are_caught_and_named(self, sector, industry, expected):
        assert excluded_by(sector, industry) == expected

    @pytest.mark.parametrize(
        "sector,industry",
        [
            ("Technology", "Software - Application"),
            ("Industrials", "Specialty Business Services"),
            ("Healthcare", "Medical Devices"),
            ("Industrials", "Specialty Industrial Machinery"),
            ("Consumer Defensive", "Packaged Foods"),
        ],
    )
    def test_ordinary_businesses_pass_through(self, sector, industry):
        """An over-broad pattern that quietly empties the screen is the main risk."""
        assert excluded_by(sector, industry) is None

    def test_it_names_the_principle_rather_than_returning_a_boolean(self):
        """A row has to be able to say which rule removed it.

        "Excluded" with no reason is indistinguishable from having failed on
        the arithmetic, and the reader cannot tell an ethical line from a
        quality one.
        """
        got = excluded_by("Consumer Defensive", "Tobacco")
        assert got in principles.EXCLUSION_PATTERNS

    def test_missing_labels_do_not_exclude(self):
        """Absent data is not evidence of a vice business."""
        assert excluded_by(None, None) is None
        assert excluded_by("", "") is None


class TestRegistryHonesty:
    def test_every_principle_states_how_it_is_enforced_and_why(self):
        for p in principles.REGISTRY:
            assert p.statement.strip(), f"{p.id} has no statement"
            assert p.enforced.strip(), f"{p.id} does not say how it is enforced"
            assert p.why.strip(), (
                f"{p.id} has no reason. A principle without one is a preference "
                "that gets abandoned the first time it costs something."
            )

    def test_principle_ids_are_unique(self):
        ids = [p.id for p in principles.REGISTRY]
        assert len(ids) == len(set(ids))

    def test_an_unenforced_principle_is_not_filed_as_enforceable(self):
        """The one that matters.

        `developed-markets-only` is true today only because of which universes
        exist. Filing it under `universe` would assert a check that does not
        run — the machine-readable version of the bug this whole session has
        been about, where the compounder read as a large-cap screen purely
        because of its default universe.
        """
        geo = next(p for p in principles.REGISTRY if p.id == "developed-markets-only")
        assert geo.kind == "judgment"
        assert "NOT ENFORCED" in geo.enforced

    def test_nothing_claims_to_be_a_universe_rule_while_none_is_enforced(self):
        """There is no universe-load check yet, so nothing may claim one.

        When one is built, this test is what tells you to come back and
        reclassify the geography principle rather than leaving it as prose.
        """
        assert principles.BY_KIND["universe"] == (), (
            "a principle is filed as a universe rule but no universe-load check "
            "exists to enforce it"
        )

    def test_every_exclusion_principle_has_a_pattern_behind_it(self):
        """An exclusion in the registry with no matcher enforces nothing."""
        for p in principles.BY_KIND["exclusion"]:
            if p.id == "no-commodity-price-takers":
                continue  # lives in the compounder's own avoid-list, by design
            assert p.id in principles.EXCLUSION_PATTERNS, (
                f"{p.id} is registered as an exclusion but has no pattern"
            )

    def test_judgments_are_not_silently_scored(self):
        """These go to the committee and are recorded as unchecked.

        If one ever acquires a numeric threshold it has stopped being a
        judgment and must be reclassified, not quietly scored alongside the
        measurements.
        """
        for p in principles.judgments():
            assert "NOT" in p.enforced or "PARTLY" in p.enforced, (
                f"{p.id} is filed as a judgment but its `enforced` text does not "
                "say what is missing"
            )


def test_the_exclusions_are_inside_every_screen_fingerprint():
    """They change what a screen returns, so they are part of its rules.

    Without this, adding a vice exclusion re-scores every cached run while
    every cache goes on reporting itself as current.
    """
    # Read off the registry rather than typed out. The list was hardcoded and
    # would have gone on passing with a fifth screen that fingerprinted none
    # of them, which is the failure this test exists to catch.
    for screen in sorted(criteria.REGISTRY):
        crit = criteria.criteria_for(screen) or {}
        keys = {k for k in crit if k.startswith("exclusion:")}
        assert keys == {f"exclusion:{pid}" for pid in principles.EXCLUSION_PATTERNS}, (
            f"{screen} does not fingerprint the standing exclusions"
        )


def test_changing_an_exclusion_moves_every_fingerprint(monkeypatch):
    import re

    before = {s: criteria.fingerprint(s) for s in criteria.REGISTRY}
    monkeypatch.setitem(
        principles.EXCLUSION_PATTERNS, "vice", re.compile(r"something-else", re.IGNORECASE)
    )
    after = {s: criteria.fingerprint(s) for s in criteria.REGISTRY}
    assert all(before[s] != after[s] for s in before), (
        "a screen's fingerprint did not move when a shared exclusion changed"
    )
