from hedge_fund.decisions.store import calibration, score


def _d(conviction, action, move):
    return {
        "conviction": conviction,
        "action": action,
        "outcome": {"scored": True, "vs_index_pct": move},
    }


def test_monotonic_when_conviction_pays():
    out = calibration([_d(30, "buy", -2), _d(60, "buy", 1), _d(90, "sell", 5), _d(80, "buy", 3)])
    assert out["n"] == 4
    assert [b["n"] for b in out["bands"]] == [1, 1, 2]
    assert out["bands"][2]["mean_vs_index_pct"] == 4.0
    assert out["bands"][2]["hit_rate_pct"] == 100.0
    assert out["monotonic"] is True


def test_inverted_and_filtered():
    rows = [
        _d(30, "buy", 5),
        _d(60, "buy", 1),
        _d(90, "buy", -3),
        _d(90, "hold", 50),  # not a directional call
        {"conviction": 90, "action": "buy", "outcome": {"scored": False}},
        _d(None, "buy", 9),
    ]
    out = calibration(rows)
    assert out["n"] == 3
    assert out["monotonic"] is False


def test_empty_band_is_unknown():
    assert calibration([_d(90, "buy", 2)])["monotonic"] is None


def test_calls_without_an_index_price_are_counted_not_scored():
    rows = [_d(90, "buy", 2), {"conviction": 90, "action": "buy", "outcome": {"scored": True}}]
    out = calibration(rows)
    assert out["n"] == 1
    assert out["n_without_index"] == 1
    assert out["hit_rate_pct"] == 100.0


def _call(action):
    return {
        "action": action,
        "price_at_decision": 100.0,
        "portfolio_context": {"benchmark": {"ticker": "SPY", "price": 500.0}},
    }


def test_a_buy_that_rose_less_than_the_index_is_a_miss():
    # Stock +10%, index +20%: up in price, behind the market.
    out = score(_call("buy"), 110.0, 600.0)
    assert out["in_your_favour_pct"] == 10.0
    assert out["benchmark_move_pct"] == 20.0
    assert out["vs_index_pct"] == -10.0


def test_a_pass_on_a_laggard_is_a_hit():
    assert score(_call("pass"), 110.0, 600.0)["vs_index_pct"] == 10.0


def test_no_index_price_leaves_vs_index_empty():
    assert (
        score({"action": "buy", "price_at_decision": 100.0}, 110.0, 600.0)["vs_index_pct"] is None
    )
