"""Portfolio and guardrail unit tests (no network)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hedge_fund.db import models  # noqa: F401 — register ORM mappers
from hedge_fund.db.models import Account
from hedge_fund.db.session import Base
from hedge_fund.portfolio import service as ps


@pytest.fixture
def memory_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_guardrail_ticker():
    from hedge_fund.agents.guardrails import GuardrailError, sanitize_ticker

    assert sanitize_ticker("  aapl  ") == "AAPL"
    with pytest.raises(GuardrailError):
        sanitize_ticker("DROP TABLE")


def test_buy_and_sell(memory_session):
    db = memory_session
    acc = Account(name="T", cash_balance=Decimal("10000"), currency="USD")
    db.add(acc)
    db.commit()
    db.refresh(acc)

    ps.record_buy(db, acc.id, "AAPL", Decimal("10"), Decimal("100"), fee=Decimal("1"))
    acc = db.get(Account, acc.id)
    assert acc.cash_balance == Decimal("10000") - Decimal("1001")

    ps.record_sell(db, acc.id, "AAPL", Decimal("10"), Decimal("110"), fee=Decimal("0"))
    acc = db.get(Account, acc.id)
    assert acc.cash_balance == Decimal("10000") - Decimal("1001") + Decimal("1100")


def test_list_transactions_orders_newest_first_and_caps(memory_session):
    """The ledger page is bounded and ordered, regardless of what the caller asks."""
    db = memory_session
    acc = Account(name="T", cash_balance=Decimal("100000"), currency="USD")
    db.add(acc)
    db.commit()
    db.refresh(acc)

    for i in range(5):
        ps.record_buy(db, acc.id, f"T{i}", Decimal("1"), Decimal("10"), fee=Decimal("0"))

    rows = ps.list_transactions(db, acc.id, limit=3)
    assert len(rows) == 3
    executed = [r.executed_at for r in rows]
    assert executed == sorted(executed, reverse=True)

    # An over-large limit is clamped rather than honoured, so one caller cannot
    # ask for the whole ledger at once.
    assert len(ps.list_transactions(db, acc.id, limit=10_000)) == 5


def test_transaction_out_matches_the_orm_row(memory_session):
    """The wire schema is the only definition of the ledger shape.

    Regression test: the route used to hand-roll this mapping alongside an unused
    `TransactionOut`, so a new column could land on the model and reach the API
    through neither.
    """
    from hedge_fund.portfolio.schemas import TransactionOut

    db = memory_session
    acc = Account(name="T", cash_balance=Decimal("10000"), currency="USD")
    db.add(acc)
    db.commit()
    db.refresh(acc)

    ps.record_buy(db, acc.id, "AAPL", Decimal("2"), Decimal("50"), fee=Decimal("1"))
    row = ps.list_transactions(db, acc.id)[0]
    out = TransactionOut.model_validate(row)

    assert out.ticker == "AAPL"
    assert out.shares == 2.0
    assert out.price_per_share == 50.0
    assert out.fee == 1.0
    assert out.cash_delta == float(row.cash_delta)
    assert out.executed_at == row.executed_at
