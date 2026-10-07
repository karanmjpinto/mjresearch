"""The constraint flow: does it conserve, and does it order the argument.

A Sankey is only honest if the quantity conserves at every split. These tests
assert that first, because a drawing whose ribbons do not add up is worse than
no drawing — it looks like evidence. The rest guard the two claims the chart
makes by construction: that the width is a count of companies and never a
money figure nobody sourced, and that each system is ordered tightest first,
which is the whole reason the picture is worth looking at.
"""

from __future__ import annotations

import pytest

from hedge_fund.constraints.catalogue import CatalogueError, live
from hedge_fund.constraints.flow import BAND_ORDER, SYSTEM_ORDER, exposure_flow, tightness


@pytest.fixture(scope="module")
def flow() -> dict:
    try:
        return exposure_flow()
    except CatalogueError as exc:
        pytest.skip(f"constraint catalogue unusable: {exc}")


def test_total_conserves_across_every_split(flow: dict) -> None:
    """The one property a Sankey cannot be wrong about."""
    by_system = sum(s["value"] for s in flow["systems"])
    by_band = sum(b["value"] for b in flow["bands"])
    by_constraint = sum(c["value"] for s in flow["systems"] for c in s["constraints"])
    assert flow["total"] == by_system == by_band == by_constraint


def test_each_system_equals_its_constraints(flow: dict) -> None:
    for s in flow["systems"]:
        assert s["value"] == sum(c["value"] for c in s["constraints"]), s["id"]


def test_each_constraint_equals_its_bands(flow: dict) -> None:
    """A terminal bar is drawn as band segments, so they must fill it exactly."""
    for s in flow["systems"]:
        for c in s["constraints"]:
            assert c["value"] == sum(c["bands"][b] for b in BAND_ORDER), c["id"]


def test_systems_come_back_in_the_fixed_order(flow: dict) -> None:
    order = [s["id"] for s in flow["systems"]]
    assert order == [s for s in SYSTEM_ORDER if s in order]


def test_each_system_is_ordered_tightest_first(flow: dict) -> None:
    """The ordering is the argument — if it drifts, the chart stops saying anything."""
    for s in flow["systems"]:
        measured = [c["tightness"] for c in s["constraints"] if c["tightness"] is not None]
        assert measured == sorted(measured, reverse=True), s["id"]
        # Anything unmeasured sorts to the end rather than to a default value.
        seen_unmeasured = False
        for c in s["constraints"]:
            if c["tightness"] is None:
                seen_unmeasured = True
            elif seen_unmeasured:
                pytest.fail(f"{s['id']}: a measured constraint sorted after an unmeasured one")


def test_width_is_a_count_not_money(flow: dict) -> None:
    """Every value is a whole number of companies, and the caption says so."""
    assert flow["unit"] == "named exposures"
    assert "not money" in flow["note"]
    for s in flow["systems"]:
        assert isinstance(s["value"], int)
        for c in s["constraints"]:
            assert isinstance(c["value"], int)
            assert c["value"] >= 1


def test_only_live_constraints_with_names_are_drawn(flow: dict) -> None:
    drawn = {c["id"] for s in flow["systems"] for c in s["constraints"]}
    for c in live():
        if c.verdict == "rejected":
            assert c.id not in drawn
        elif not c.names:
            assert c.id not in drawn, f"{c.id} has no names and cannot carry a ribbon"


def test_tightness_is_a_multiple_of_normal_or_nothing() -> None:
    """No `normal`, no number — never a default that would place it anyway."""
    for c in live():
        t = tightness(c)
        if t is None:
            assert not [m for m in c.measurements if m.normal], c.id
        else:
            assert t > 0
            assert t == max(
                m.value / m.normal
                for m in c.measurements
                if m.normal is not None and m.normal != 0 and m.value is not None
            )


def test_unmeasured_are_named_rather_than_dropped(flow: dict) -> None:
    drawn = {c["id"] for s in flow["systems"] for c in s["constraints"]}
    for cid in flow["unmeasured"]:
        assert cid in drawn, "an unmeasured constraint is still drawn, just not ranked"


def test_the_finding_the_chart_exists_to_show(flow: dict) -> None:
    """Tighter constraints have fewer listed ways to own them.

    Stated as a test because it is the chart's reason to exist. If the
    catalogue grows and this stops holding, the caption claiming it is wrong
    and this should fail rather than the page quietly misleading someone.
    """
    pairs = [
        (c["tightness"], c["value"])
        for s in flow["systems"]
        for c in s["constraints"]
        if c["tightness"] is not None
    ]
    tightest = [v for t, v in pairs if t >= 3.0]
    loosest = [v for t, v in pairs if t < 2.0]
    assert tightest and loosest
    assert sum(tightest) / len(tightest) < sum(loosest) / len(loosest)
