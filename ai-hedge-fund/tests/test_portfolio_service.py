"""Ledger arithmetic: trades, cash, and corporate actions.

These functions mutate the book. An error here does not raise — it produces a
slightly wrong cost basis that every later valuation, return figure and risk
number silently inherits, and there is no downstream check that would catch it.
That is why the assertions below are mostly *invariants* (what a corporate
action must not change) rather than expected values.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hedge_fund.db import models  # noqa: F401 — register ORM mappers
from hedge_fund.db.models import Account, CorporateAction, Transaction
from hedge_fund.db.session import Base
from hedge_fund.portfolio import service as ps


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def account(db):
    acc = Account(name="T", cash_balance=Decimal("100000"), currency="USD")
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def _hold(db, account_id, ticker="AAPL", shares="100", price="50"):
    ps.record_buy(db, account_id, ticker, Decimal(shares), Decimal(price))
    return ps.get_holding(db, account_id, ticker)


# ----------------------------------------------------------------------
# Stock splits
# ----------------------------------------------------------------------


@pytest.mark.parametrize("ratio", ["2", "4", "10"])
def test_forward_split_preserves_cost_basis(db, account, ratio):
    """The invariant that matters: a split moves no money.

    Shares go up and cost per share goes down by the same factor, so
    `shares * avg_cost` — what the position cost — is unchanged. Get this wrong
    and every unrealised P&L figure after it is wrong by the same factor.
    """
    row = _hold(db, account.id)
    before = row.shares * row.avg_cost
    cash_before = account.cash_balance

    ps.apply_stock_split(db, account.id, "AAPL", Decimal(ratio))

    row = ps.get_holding(db, account.id, "AAPL")
    assert row.shares == Decimal("100") * Decimal(ratio)
    assert row.shares * row.avg_cost == pytest.approx(float(before))
    assert account.cash_balance == cash_before, "a split is not a cash event"


def test_reverse_split_preserves_cost_basis(db, account):
    """ratio < 1 is a reverse split: fewer shares, proportionally dearer."""
    row = _hold(db, account.id, shares="100", price="50")
    before = row.shares * row.avg_cost

    ps.apply_stock_split(db, account.id, "AAPL", Decimal("0.5"))

    row = ps.get_holding(db, account.id, "AAPL")
    assert row.shares == Decimal("50")
    assert row.avg_cost == Decimal("100")
    assert row.shares * row.avg_cost == before


def test_split_records_a_corporate_action_and_a_ledger_entry(db, account):
    _hold(db, account.id)
    ps.apply_stock_split(db, account.id, "AAPL", Decimal("2"))

    actions = db.query(CorporateAction).all()
    assert len(actions) == 1
    assert actions[0].split_ratio == Decimal("2")
    assert actions[0].applied is True

    split_txns = [t for t in db.query(Transaction).all() if t.ticker == "AAPL" and t.shares is None]
    assert len(split_txns) == 1
    assert split_txns[0].cash_delta == Decimal("0")
    assert split_txns[0].meta == {"ratio": 2.0}


@pytest.mark.parametrize("bad", ["0", "-1"])
def test_split_rejects_non_positive_ratio(db, account, bad):
    _hold(db, account.id)
    with pytest.raises(ValueError, match="ratio must be positive"):
        ps.apply_stock_split(db, account.id, "AAPL", Decimal(bad))


def test_split_rejects_unheld_ticker(db, account):
    with pytest.raises(ValueError, match="no holding"):
        ps.apply_stock_split(db, account.id, "NOPE", Decimal("2"))


# ----------------------------------------------------------------------
# Cash dividends
# ----------------------------------------------------------------------


def test_dividend_pays_per_share_and_leaves_the_position_alone(db, account):
    _hold(db, account.id, shares="200", price="10")
    cash_before = account.cash_balance

    out = ps.apply_cash_dividend(db, account.id, "AAPL", Decimal("0.25"))

    assert out["cash_received"] == pytest.approx(50.0)
    assert account.cash_balance == cash_before + Decimal("50")

    row = ps.get_holding(db, account.id, "AAPL")
    assert row.shares == Decimal("200"), "a cash dividend does not change share count"
    assert row.avg_cost == Decimal("10"), "nor the cost basis"


def test_dividend_after_split_pays_on_the_new_share_count(db, account):
    """Ordering matters: the split must be reflected before the dividend lands."""
    _hold(db, account.id, shares="100", price="50")
    ps.apply_stock_split(db, account.id, "AAPL", Decimal("2"))

    out = ps.apply_cash_dividend(db, account.id, "AAPL", Decimal("1"))
    assert out["cash_received"] == pytest.approx(200.0)


def test_dividend_rejects_unheld_ticker(db, account):
    with pytest.raises(ValueError, match="no holding"):
        ps.apply_cash_dividend(db, account.id, "NOPE", Decimal("1"))


# ----------------------------------------------------------------------
# Cash
# ----------------------------------------------------------------------


def test_deposit_and_withdraw_move_cash_both_ways(db, account):
    ps.record_cash(db, account.id, Decimal("500"), deposit=True)
    assert account.cash_balance == Decimal("100500")

    ps.record_cash(db, account.id, Decimal("300"), deposit=False)
    assert account.cash_balance == Decimal("100200")


def test_withdrawal_beyond_the_balance_is_refused(db, account):
    with pytest.raises(ValueError, match="insufficient cash"):
        ps.record_cash(db, account.id, Decimal("100001"), deposit=False)
    assert account.cash_balance == Decimal("100000"), "a refused withdrawal moves nothing"


# ----------------------------------------------------------------------
# Buys and sells
# ----------------------------------------------------------------------


def test_buying_twice_averages_the_cost(db, account):
    ps.record_buy(db, account.id, "AAPL", Decimal("100"), Decimal("10"))
    ps.record_buy(db, account.id, "AAPL", Decimal("100"), Decimal("20"))

    row = ps.get_holding(db, account.id, "AAPL")
    assert row.shares == Decimal("200")
    assert row.avg_cost == Decimal("15")


def test_buy_fee_leaves_the_book_but_not_the_cost_basis(db, account):
    """The fee is a cash cost, and must not be smuggled into avg_cost."""
    ps.record_buy(db, account.id, "AAPL", Decimal("10"), Decimal("100"), fee=Decimal("7"))

    assert account.cash_balance == Decimal("100000") - Decimal("1007")
    assert ps.get_holding(db, account.id, "AAPL").avg_cost == Decimal("100")


def test_partial_sell_keeps_the_remainder_at_the_same_basis(db, account):
    _hold(db, account.id, shares="100", price="50")
    cash_before = account.cash_balance

    ps.record_sell(db, account.id, "AAPL", Decimal("40"), Decimal("60"))

    row = ps.get_holding(db, account.id, "AAPL")
    assert row.shares == Decimal("60")
    assert row.avg_cost == Decimal("50"), "selling does not re-price what is left"
    assert account.cash_balance == cash_before + Decimal("2400")


def test_selling_out_removes_the_position(db, account):
    _hold(db, account.id, shares="100", price="50")
    ps.record_sell(db, account.id, "AAPL", Decimal("100"), Decimal("55"))
    assert ps.get_holding(db, account.id, "AAPL") is None


def test_sell_fee_comes_out_of_proceeds(db, account):
    _hold(db, account.id, shares="100", price="50")
    cash_before = account.cash_balance

    ps.record_sell(db, account.id, "AAPL", Decimal("10"), Decimal("60"), fee=Decimal("5"))
    assert account.cash_balance == cash_before + Decimal("595")


def test_overselling_is_refused_and_changes_nothing(db, account):
    _hold(db, account.id, shares="100", price="50")
    cash_before = account.cash_balance

    with pytest.raises(ValueError, match="insufficient shares"):
        ps.record_sell(db, account.id, "AAPL", Decimal("101"), Decimal("60"))

    assert ps.get_holding(db, account.id, "AAPL").shares == Decimal("100")
    assert account.cash_balance == cash_before


def test_selling_an_unheld_ticker_is_refused(db, account):
    with pytest.raises(ValueError, match="insufficient shares"):
        ps.record_sell(db, account.id, "NOPE", Decimal("1"), Decimal("10"))


# ----------------------------------------------------------------------
# Views (market data stubbed — these tests are about the arithmetic, not the feed)
# ----------------------------------------------------------------------


class _StubDataService:
    """Returns a flat price series, so any movement in the output is the code's."""

    def __init__(self, price: float):
        self.price = price

    def get_price_history(self, ticker, days=5, **kwargs):
        import pandas as pd

        return pd.DataFrame({"close": [self.price] * max(days, 2)})


def test_portfolio_view_marks_positions_and_totals_them(db, account, monkeypatch):
    monkeypatch.setattr(ps, "_ds", _StubDataService(75.0))
    _hold(db, account.id, shares="100", price="50")

    view = ps.build_portfolio_view(db, account.id)
    pos = next(h for h in view["holdings"] if h["ticker"] == "AAPL")

    assert pos["current_price"] == pytest.approx(75.0)
    assert pos["market_value"] == pytest.approx(7500.0)
    # Bought 100 @ 50, marked at 75.
    assert pos["pnl"] == pytest.approx(2500.0)
    assert pos["pnl_pct"] == pytest.approx(50.0)
    assert view["total_value"] == pytest.approx(float(account.cash_balance) + 7500.0)
    assert view["holdings_count"] == 1
    # Weights are of total value, cash included, and must account for all of it.
    assert pos["weight_pct"] + view["cash_pct"] == pytest.approx(100.0, abs=0.02)


def test_portfolio_view_of_an_empty_book_is_all_cash(db, account, monkeypatch):
    monkeypatch.setattr(ps, "_ds", _StubDataService(75.0))

    view = ps.build_portfolio_view(db, account.id)
    assert view["holdings"] == []
    assert view["holdings_count"] == 0
    assert view["total_value"] == pytest.approx(float(account.cash_balance))
    assert view["cash_pct"] == pytest.approx(100.0)


def test_risk_on_a_flat_series_reports_no_volatility(db, account, monkeypatch):
    """A constant price has zero return variance; risk must be finite, not NaN."""
    import math

    monkeypatch.setattr(ps, "_ds", _StubDataService(75.0))
    _hold(db, account.id, shares="100", price="50")

    risk = ps.risk_weighted(db, account.id)
    for key, value in risk.items():
        if isinstance(value, float):
            assert not math.isnan(value), f"{key} is NaN"
            assert not math.isinf(value), f"{key} is infinite"
