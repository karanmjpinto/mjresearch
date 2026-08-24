"""Portfolio math, transactions, corporate actions, weighted risk."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from hedge_fund.data.service import get_data_service
from hedge_fund.db.models import Account, CorporateAction, Holding, Transaction, TxnType
from hedge_fund.db.models import CorporateActionType as CAType

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
_ds = get_data_service()

Q = Decimal("0.00000001")


def _finite_float(x: float, fallback: float) -> float:
    """JSON responses cannot contain NaN or inf."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return fallback
    return v if math.isfinite(v) else fallback


def _d(x: Any) -> Decimal:
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def get_or_create_default_account(db: Session) -> Account:
    acc = db.execute(select(Account).limit(1)).scalar_one_or_none()
    if acc:
        return acc
    acc = Account(name="Primary", cash_balance=Decimal("0"), currency="USD", benchmark="SPY")
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def seed_from_portfolio_json(db: Session) -> bool:
    """If DB has no holdings, import `config/portfolio.json`. Returns True if import ran."""
    acc = get_or_create_default_account(db)
    n = db.execute(select(Holding).where(Holding.account_id == acc.id)).scalars().first()
    if n is not None:
        return False
    path = CONFIG_DIR / "portfolio.json"
    if not path.exists():
        return False
    with open(path) as f:
        data = json.load(f)
    acc.cash_balance = _d(data.get("cash", 0))
    acc.currency = data.get("currency", "USD")
    acc.benchmark = data.get("benchmark")
    for h in data.get("holdings", []):
        db.add(
            Holding(
                account_id=acc.id,
                ticker=str(h["ticker"]).upper(),
                shares=_d(h["shares"]),
                avg_cost=_d(h["avg_cost"]),
                currency=h.get("currency", "USD"),
            )
        )
    db.add(
        Transaction(
            account_id=acc.id,
            txn_type=TxnType.SEED,
            ticker=None,
            cash_delta=Decimal("0"),
            note="Imported from portfolio.json",
            meta={"source": "portfolio.json"},
        )
    )
    db.commit()
    return True


def _get_holding(db: Session, account_id: int, ticker: str) -> Holding | None:
    return db.execute(
        select(Holding).where(Holding.account_id == account_id, Holding.ticker == ticker.upper())
    ).scalar_one_or_none()


def get_holding(db: Session, account_id: int, ticker: str) -> Holding | None:
    return _get_holding(db, account_id, ticker)


#: Hard ceiling on a ledger page, whatever the caller asks for.
TRANSACTIONS_MAX = 500


def list_transactions(db: Session, account_id: int, *, limit: int = 100) -> list[Transaction]:
    """Most recent ledger entries first.

    Rows come back as ORM objects rather than dicts: the wire shape belongs to
    `schemas.TransactionOut`, and returning it from here would give the ledger
    two definitions that have to be kept in agreement by hand.
    """
    return list(
        db.execute(
            select(Transaction)
            .where(Transaction.account_id == account_id)
            .order_by(Transaction.executed_at.desc())
            .limit(min(limit, TRANSACTIONS_MAX))
        )
        .scalars()
        .all()
    )


def record_buy(
    db: Session,
    account_id: int,
    ticker: str,
    shares: Decimal,
    price: Decimal,
    fee: Decimal = Decimal("0"),
    note: str | None = None,
) -> dict[str, Any]:
    ticker = ticker.upper()
    cost = shares * price + fee
    acc = db.get(Account, account_id)
    if acc is None:
        raise ValueError("account not found")
    if acc.cash_balance < cost:
        raise ValueError("insufficient cash")

    acc.cash_balance -= cost
    row = _get_holding(db, account_id, ticker)
    if row is None:
        db.add(
            Holding(
                account_id=account_id,
                ticker=ticker,
                shares=shares,
                avg_cost=price,
                currency=acc.currency,
            )
        )
    else:
        total_sh = row.shares + shares
        row.avg_cost = (row.shares * row.avg_cost + shares * price) / total_sh
        row.shares = total_sh

    db.add(
        Transaction(
            account_id=account_id,
            txn_type=TxnType.BUY,
            ticker=ticker,
            shares=shares,
            price_per_share=price,
            fee=fee,
            cash_delta=-cost,
            note=note,
        )
    )
    db.commit()
    return {"ok": True, "ticker": ticker}


def record_sell(
    db: Session,
    account_id: int,
    ticker: str,
    shares: Decimal,
    price: Decimal,
    fee: Decimal = Decimal("0"),
    note: str | None = None,
) -> dict[str, Any]:
    ticker = ticker.upper()
    row = _get_holding(db, account_id, ticker)
    if row is None or row.shares < shares:
        raise ValueError("insufficient shares")

    proceeds = shares * price - fee
    acc = db.get(Account, account_id)
    if acc is None:
        raise ValueError("account not found")
    acc.cash_balance += proceeds

    row.shares -= shares
    if row.shares <= Q:
        db.delete(row)

    db.add(
        Transaction(
            account_id=account_id,
            txn_type=TxnType.SELL,
            ticker=ticker,
            shares=shares,
            price_per_share=price,
            fee=fee,
            cash_delta=proceeds,
            note=note,
        )
    )
    db.commit()
    return {"ok": True, "ticker": ticker}


def record_cash(
    db: Session,
    account_id: int,
    amount: Decimal,
    *,
    deposit: bool,
    note: str | None = None,
) -> dict[str, Any]:
    acc = db.get(Account, account_id)
    if acc is None:
        raise ValueError("account not found")
    if not deposit and acc.cash_balance < amount:
        raise ValueError("insufficient cash")
    delta = amount if deposit else -amount
    acc.cash_balance += delta
    db.add(
        Transaction(
            account_id=account_id,
            txn_type=TxnType.CASH_DEPOSIT if deposit else TxnType.CASH_WITHDRAW,
            cash_delta=delta,
            note=note,
        )
    )
    db.commit()
    return {"ok": True, "cash_balance": float(acc.cash_balance)}


def apply_stock_split(
    db: Session,
    account_id: int,
    ticker: str,
    ratio: Decimal,
    *,
    ex_date: date | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Forward split: ratio=4 means 4 new shares per 1 old (4:1). Adjusts shares up, cost/share down."""
    ticker = ticker.upper()
    if ratio <= 0:
        raise ValueError("ratio must be positive")

    row = _get_holding(db, account_id, ticker)
    if row is None:
        raise ValueError("no holding for ticker")

    row.shares *= ratio
    row.avg_cost /= ratio

    ca = CorporateAction(
        account_id=account_id,
        ticker=ticker,
        action_type=CAType.STOCK_SPLIT,
        ex_date=ex_date or date.today(),
        split_ratio=ratio,
        applied=True,
        note=note,
    )
    db.add(ca)
    db.add(
        Transaction(
            account_id=account_id,
            txn_type=TxnType.SPLIT,
            ticker=ticker,
            cash_delta=Decimal("0"),
            note=f"Stock split {ratio}:1",
            meta={"ratio": float(ratio)},
        )
    )
    db.commit()
    return {
        "ok": True,
        "ticker": ticker,
        "shares": float(row.shares),
        "avg_cost": float(row.avg_cost),
    }


def apply_cash_dividend(
    db: Session,
    account_id: int,
    ticker: str,
    per_share: Decimal,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ticker = ticker.upper()
    row = _get_holding(db, account_id, ticker)
    if row is None:
        raise ValueError("no holding for ticker")

    amount = row.shares * per_share
    acc = db.get(Account, account_id)
    if acc is None:
        raise ValueError("account not found")
    acc.cash_balance += amount

    ca = CorporateAction(
        account_id=account_id,
        ticker=ticker,
        action_type=CAType.CASH_DIVIDEND,
        dividend_per_share=per_share,
        applied=True,
        note=note,
    )
    db.add(ca)
    db.add(
        Transaction(
            account_id=account_id,
            txn_type=TxnType.DIVIDEND,
            ticker=ticker,
            cash_delta=amount,
            note=note or f"Dividend {per_share}/share",
            meta={"per_share": float(per_share)},
        )
    )
    db.commit()
    return {"ok": True, "cash_received": float(amount)}


@dataclass
class PositionSnapshot:
    ticker: str
    shares: float
    avg_cost: float
    currency: str
    current_price: float
    market_value: float
    pnl: float
    pnl_pct: float
    weight_pct: float


def build_portfolio_view(db: Session, account_id: int) -> dict[str, Any]:
    acc = db.get(Account, account_id)
    if acc is None:
        raise ValueError("account not found")
    rows = db.execute(select(Holding).where(Holding.account_id == account_id)).scalars().all()

    holdings: list[PositionSnapshot] = []
    total_mv = float(acc.cash_balance)

    for h in rows:
        fallback = float(h.avg_cost)
        try:
            df = _ds.get_price_history(h.ticker, days=5)
            if not df.empty:
                current = float(df["close"].iloc[-1])
            else:
                current = fallback
        except Exception as e:
            logger.warning("price for %s: %s", h.ticker, e)
            current = fallback

        current = _finite_float(current, fallback)
        sh = float(h.shares)
        mv = _finite_float(current * sh, 0.0)
        cost = _finite_float(float(h.avg_cost) * sh, 0.0)
        pnl = _finite_float(mv - cost, 0.0)
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0.0
        total_mv += mv
        holdings.append(
            PositionSnapshot(
                ticker=h.ticker,
                shares=sh,
                avg_cost=float(h.avg_cost),
                currency=h.currency,
                current_price=current,
                market_value=mv,
                pnl=pnl,
                pnl_pct=pnl_pct,
                weight_pct=0.0,
            )
        )

    cash0 = _finite_float(float(acc.cash_balance), 0.0)
    total_mv = _finite_float(total_mv, cash0)

    for h in holdings:
        h.weight_pct = (h.market_value / total_mv * 100) if total_mv > 0 else 0.0
        h.weight_pct = _finite_float(h.weight_pct, 0.0)

    cash_pct = (cash0 / total_mv * 100) if total_mv > 0 else 0.0

    return {
        "total_value": round(total_mv, 2),
        "cash": cash0,
        "cash_pct": round(_finite_float(cash_pct, 0.0), 2),
        "currency": acc.currency,
        "benchmark": acc.benchmark,
        "holdings_count": len(holdings),
        "holdings": [
            {
                "ticker": h.ticker,
                "shares": round(h.shares, 6),
                "avg_cost": round(h.avg_cost, 4),
                "currency": h.currency,
                "current_price": round(h.current_price, 4),
                "market_value": round(h.market_value, 2),
                "pnl": round(h.pnl, 2),
                "pnl_pct": round(h.pnl_pct, 2),
                "weight_pct": round(h.weight_pct, 2),
            }
            for h in holdings
        ],
    }


def risk_weighted(db: Session, account_id: int, *, days: int = 252) -> dict[str, Any]:
    """Value-weighted daily portfolio returns → VaR, Sharpe, max drawdown."""
    acc = db.get(Account, account_id)
    if acc is None:
        raise ValueError("account not found")
    rows = db.execute(select(Holding).where(Holding.account_id == account_id)).scalars().all()
    if not rows:
        return {"error": "no holdings for risk calculation"}

    prices: list[np.ndarray] = []
    live_mv: list[float] = []

    # A holding with no usable price history cannot enter the calculation, and
    # the weights below are renormalised over whatever is left. That silently
    # reports the risk of a subset as the risk of the book — a portfolio with
    # half its positions unpriced would read as a complete, and much tidier,
    # answer. Keep the exclusions and return them.
    excluded: list[dict[str, str]] = []

    for h in rows:
        try:
            df = _ds.get_price_history(h.ticker, days=days)
            if df.empty or len(df) < 10:
                excluded.append({"ticker": h.ticker, "reason": "insufficient price history"})
                continue
            ret = df["close"].pct_change().dropna().values
            prices.append(ret)
            cur = float(df["close"].iloc[-1])
            mv = cur * float(h.shares)
            live_mv.append(mv)
        except Exception as exc:
            logger.warning("risk: excluding %s — %s", h.ticker, exc)
            excluded.append({"ticker": h.ticker, "reason": str(exc)[:200]})
            continue

    if not prices or not live_mv:
        return {"error": "insufficient price history", "excluded": excluded}

    w = np.array(live_mv, dtype=float)
    w = w / w.sum()
    min_len = min(len(p) for p in prices)
    stacked = np.column_stack([p[-min_len:] for p in prices])
    port_ret = (stacked * w).sum(axis=1)

    var_95 = float(np.percentile(port_ret, 5))
    mask = port_ret <= var_95
    cvar = float(port_ret[mask].mean()) if mask.any() else var_95
    std = float(port_ret.std())
    sharpe = float(port_ret.mean() / std * math.sqrt(252)) if std > 0 else 0.0
    cum = np.cumprod(1 + port_ret)
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    max_dd = float(dd.min())

    limits_path = CONFIG_DIR / "risk_limits.json"
    limits: dict = {}
    if limits_path.exists():
        with open(limits_path) as f:
            limits = json.load(f)

    return {
        "var_95_daily": round(abs(var_95) * 100, 4),
        "cvar_95_daily": round(abs(cvar) * 100, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown_pct": round(abs(max_dd) * 100, 4),
        "observations": min_len,
        "method": "value_weighted_returns",
        "limits": limits,
        # What the figures above do *not* cover. `positions_priced` against the
        # book's own count is the reader's check that this is whole-portfolio
        # risk rather than the risk of the part that happened to have data.
        "positions_priced": len(prices),
        "positions_total": len(rows),
        "excluded": excluded,
    }
