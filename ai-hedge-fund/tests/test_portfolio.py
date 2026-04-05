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
