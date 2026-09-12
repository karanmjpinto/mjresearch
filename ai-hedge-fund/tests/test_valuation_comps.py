"""Comparable-company valuation ranges.

The arithmetic is one step — recover the per-share quantity from the subject's
own multiple, then apply the peers' — so these tests pin that step exactly, and
spend most of their attention on the cases that must be refused rather than
fudged.
"""

from __future__ import annotations

import pytest

from hedge_fund.valuation.comps import MULTIPLES, implied_bands, summarise


def _peers(**by_ticker: dict) -> dict[str, dict]:
    return dict(by_ticker)


def test_recovers_the_per_share_quantity_and_applies_peer_quartiles():
    # price 100 on a P/E of 20 means earnings of 5 a share. Peers at
    # 20/30/40 (the quartiles of 10..50) therefore imply 100/150/200.
    bands, dropped = implied_bands(
        100.0,
        {"pe_ratio": 20.0},
        _peers(
            A={"pe_ratio": 10.0},
            B={"pe_ratio": 20.0},
            C={"pe_ratio": 30.0},
            D={"pe_ratio": 40.0},
            E={"pe_ratio": 50.0},
        ),
    )
    assert len(bands) == 1
    b = bands[0]
    assert b.per_share == 5.0
    assert (b.peer_low, b.peer_mid, b.peer_high) == (20.0, 30.0, 40.0)
    assert (b.low, b.mid, b.high) == (100.0, 150.0, 200.0)
    assert b.peer_count == 5
    assert [d.metric for d in dropped] == ["forward_pe", "price_to_book"]


def test_a_negative_multiple_is_dropped_not_ranked_as_cheap():
    # A loss-making peer has a negative P/E. Treating -12x as cheaper than 8x
    # would rank losses as bargains, so it is excluded and the count says so.
    bands, dropped = implied_bands(
        100.0,
        {"pe_ratio": 20.0},
        _peers(
            A={"pe_ratio": 10.0},
            B={"pe_ratio": 20.0},
            C={"pe_ratio": -12.0},
            D={"pe_ratio": 30.0},
        ),
    )
    assert bands[0].peer_count == 3
    assert bands[0].peer_mid == 20.0


@pytest.mark.parametrize("bad", [0, -1, None, "n/a", float("nan"), float("inf")])
def test_unusable_peer_values_are_ignored(bad):
    bands, _ = implied_bands(
        100.0,
        {"pe_ratio": 20.0},
        _peers(
            A={"pe_ratio": 10.0},
            B={"pe_ratio": 20.0},
            C={"pe_ratio": 30.0},
            D={"pe_ratio": bad},
        ),
    )
    assert bands[0].peer_count == 3


def test_too_few_peers_produces_no_band_and_says_why():
    # A quartile drawn from two companies is decoration, and a football field
    # is read as evidence.
    bands, dropped = implied_bands(
        100.0, {"pe_ratio": 20.0}, _peers(A={"pe_ratio": 10.0}, B={"pe_ratio": 30.0})
    )
    assert bands == []
    pe = next(d for d in dropped if d.metric == "pe_ratio")
    assert pe.usable_peers == 2
    assert "3 needed" in pe.reason


def test_a_subject_without_the_multiple_cannot_be_inverted():
    bands, dropped = implied_bands(
        100.0,
        {"price_to_book": 4.0},
        _peers(
            A={"pe_ratio": 10.0, "price_to_book": 2.0},
            B={"pe_ratio": 20.0, "price_to_book": 4.0},
            C={"pe_ratio": 30.0, "price_to_book": 6.0},
        ),
    )
    assert [b.metric for b in bands] == ["price_to_book"]
    pe = next(d for d in dropped if d.metric == "pe_ratio")
    assert "subject has no positive value" in pe.reason


def test_no_price_means_no_bands_at_all():
    bands, dropped = implied_bands(
        0.0,
        {"pe_ratio": 20.0},
        _peers(A={"pe_ratio": 10.0}, B={"pe_ratio": 20.0}, C={"pe_ratio": 30.0}),
    )
    assert bands == []
    assert {d.metric for d in dropped} == {m for m, _ in MULTIPLES}
    assert all("price" in d.reason for d in dropped)


def test_bands_come_back_in_display_order():
    peers = _peers(
        A={"pe_ratio": 10.0, "forward_pe": 9.0, "price_to_book": 2.0},
        B={"pe_ratio": 20.0, "forward_pe": 18.0, "price_to_book": 4.0},
        C={"pe_ratio": 30.0, "forward_pe": 27.0, "price_to_book": 6.0},
    )
    bands, _ = implied_bands(
        100.0, {"pe_ratio": 20.0, "forward_pe": 18.0, "price_to_book": 4.0}, peers
    )
    assert [b.metric for b in bands] == ["pe_ratio", "forward_pe", "price_to_book"]


# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------


def _three_bands():
    peers = _peers(
        A={"pe_ratio": 10.0, "price_to_book": 2.0},
        B={"pe_ratio": 20.0, "price_to_book": 4.0},
        C={"pe_ratio": 30.0, "price_to_book": 6.0},
    )
    bands, _ = implied_bands(100.0, {"pe_ratio": 20.0, "price_to_book": 4.0}, peers)
    return bands


def test_summary_spans_the_widest_disagreement_rather_than_averaging_it():
    bands = _three_bands()
    s = summarise(bands, 100.0)
    assert s["low"] == min(round(b.low, 2) for b in bands)
    assert s["high"] == max(round(b.high, 2) for b in bands)
    assert s["methods"] == len(bands)


@pytest.mark.parametrize(
    ("price", "position"),
    [(100.0, "inside"), (10.0, "below the range"), (10_000.0, "above the range")],
)
def test_summary_says_where_the_price_sits(price, position):
    # The bands are built at price 100; only the comparison price moves.
    assert summarise(_three_bands(), price)["position"] == position


def test_summary_reports_upside_to_the_midpoint():
    bands = _three_bands()
    s = summarise(bands, 100.0)
    assert s["upside_to_mid_pct"] == pytest.approx(round((s["mid"] / 100.0 - 1) * 100, 1))


def test_summary_is_unavailable_rather_than_zero_when_there_is_nothing_to_say():
    # Unavailable, and it says why: a bare False leaves the caller guessing
    # whether the data was missing or the methods were rejected.
    for s_ in (summarise([], 100.0), summarise(_three_bands(), 0.0)):
        assert s_["available"] is False
        assert s_["reason"]
        assert "low" not in s_


# ------------------------------------------------------------------
# Applicability: a multiple has to compare like with like
# ------------------------------------------------------------------


def _apple_shaped_price_to_book():
    # Apple's real shape: ~45x book against peers near 6x, because buybacks
    # have left it almost no book equity.
    return implied_bands(
        332.27,
        {"pe_ratio": 38.1, "price_to_book": 45.1},
        _peers(
            MSFT={"pe_ratio": 25.9, "price_to_book": 7.3},
            GOOGL={"pe_ratio": 22.0, "price_to_book": 6.5},
            SONY={"pe_ratio": 17.7, "price_to_book": 5.6},
            DELL={"pe_ratio": 20.0, "price_to_book": 6.4},
        ),
    )


def test_a_multiple_far_from_the_peer_median_is_marked_inapplicable():
    bands, _ = _apple_shaped_price_to_book()
    pb = next(b for b in bands if b.metric == "price_to_book")
    assert pb.applicable is False
    assert "not comparing like with like" in (pb.note or "")
    # Still returned: hiding the row would be its own kind of lie.
    assert pb.mid > 0


def test_a_multiple_in_line_with_peers_stays_applicable():
    bands, _ = _apple_shaped_price_to_book()
    pe = next(b for b in bands if b.metric == "pe_ratio")
    assert pe.applicable is True
    assert pe.note is None


def test_the_summary_range_excludes_an_inapplicable_method():
    bands, _ = _apple_shaped_price_to_book()
    s = summarise(bands, 332.27)
    pb = next(b for b in bands if b.metric == "price_to_book")
    assert s["excluded"] == ["price_to_book"]
    assert s["low"] > pb.high  # the book-value row no longer drags the floor
    assert s["methods"] == 1


def test_when_no_method_applies_the_summary_says_so_rather_than_guessing():
    bands, _ = implied_bands(
        1000.0,
        {"pe_ratio": 300.0},
        _peers(A={"pe_ratio": 10.0}, B={"pe_ratio": 20.0}, C={"pe_ratio": 30.0}),
    )
    s = summarise(bands, 1000.0)
    assert s["available"] is False
    assert s["inapplicable"] == ["pe_ratio"]
