# Regression: portfolio total_value was NaN when price history contained NaN,
# causing GET /api/portfolio to 500 (JSON cannot serialize nan).
# Found by /qa on 2026-03-31
# Report: .gstack/qa-reports/qa-report-localhost-openbb-2026-03-31.md

from __future__ import annotations

import json
import math
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hedge_fund.db import models  # noqa: F401
from hedge_fund.db.models import Account, Holding
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


def test_build_portfolio_view_serializable_when_close_is_nan(memory_session, monkeypatch):
    db = memory_session
    acc = Account(name="T", cash_balance=Decimal("1000"), currency="USD")
    db.add(acc)
    db.commit()
    db.refresh(acc)
    db.add(
        Holding(
            account_id=acc.id,
            ticker="BAD",
            shares=Decimal("10"),
            avg_cost=Decimal("50"),
            currency="USD",
        )
    )
    db.commit()

    mock_ds = MagicMock()
    mock_ds.get_price_history.return_value = pd.DataFrame({"close": [float("nan")]})
    monkeypatch.setattr(ps, "_ds", mock_ds)

    view = ps.build_portfolio_view(db, acc.id)
    json.dumps(view)
    assert math.isfinite(view["total_value"])
    assert view["holdings"][0]["current_price"] == 50.0
