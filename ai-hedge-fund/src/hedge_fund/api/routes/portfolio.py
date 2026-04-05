"""Portfolio CRUD, transactions, corporate actions, weighted risk."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from hedge_fund.db.models import Account, Holding, Transaction
from hedge_fund.db.session import get_db
from hedge_fund.portfolio import service as ps
from hedge_fund.portfolio.schemas import (
    BuyRequest,
    CashRequest,
    DividendRequest,
    HoldingPatch,
    SellRequest,
    SplitRequest,
)

router = APIRouter()


def _account(db: Session) -> Account:
    ps.seed_from_portfolio_json(db)
    return ps.get_or_create_default_account(db)


@router.get("")
async def get_portfolio(db: Session = Depends(get_db)):
    acc = _account(db)
    return ps.build_portfolio_view(db, acc.id)


@router.get("/risk")
async def get_risk(db: Session = Depends(get_db)):
    acc = _account(db)
    return ps.risk_weighted(db, acc.id)


@router.get("/transactions")
async def list_transactions(limit: int = 100, db: Session = Depends(get_db)):
    acc = _account(db)
    rows = (
        db.execute(
            select(Transaction)
            .where(Transaction.account_id == acc.id)
            .order_by(Transaction.executed_at.desc())
            .limit(min(limit, 500))
        )
        .scalars()
        .all()
    )
    return {
        "transactions": [
            {
                "id": t.id,
                "txn_type": t.txn_type,
                "ticker": t.ticker,
                "shares": float(t.shares) if t.shares is not None else None,
                "price_per_share": float(t.price_per_share) if t.price_per_share is not None else None,
                "fee": float(t.fee),
                "cash_delta": float(t.cash_delta),
                "note": t.note,
                "executed_at": t.executed_at.isoformat(),
                "meta": t.meta,
            }
            for t in rows
        ]
    }


@router.post("/buy")
async def buy(req: BuyRequest, db: Session = Depends(get_db)):
    acc = _account(db)
    try:
        return ps.record_buy(
            db,
            acc.id,
            req.ticker,
            req.shares,
            req.price_per_share,
            fee=req.fee,
            note=req.note,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/sell")
async def sell(req: SellRequest, db: Session = Depends(get_db)):
    acc = _account(db)
    try:
        return ps.record_sell(
            db,
            acc.id,
            req.ticker,
            req.shares,
            req.price_per_share,
            fee=req.fee,
            note=req.note,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/cash/deposit")
async def deposit(req: CashRequest, db: Session = Depends(get_db)):
    acc = _account(db)
    try:
        return ps.record_cash(db, acc.id, req.amount, deposit=True, note=req.note)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/cash/withdraw")
async def withdraw(req: CashRequest, db: Session = Depends(get_db)):
    acc = _account(db)
    try:
        return ps.record_cash(db, acc.id, req.amount, deposit=False, note=req.note)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/corporate/split")
async def corp_split(req: SplitRequest, db: Session = Depends(get_db)):
    acc = _account(db)
    try:
        return ps.apply_stock_split(
            db,
            acc.id,
            req.ticker,
            req.ratio,
            ex_date=req.ex_date,
            note=req.note,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/corporate/dividend")
async def corp_dividend(req: DividendRequest, db: Session = Depends(get_db)):
    acc = _account(db)
    try:
        return ps.apply_cash_dividend(
            db,
            acc.id,
            req.ticker,
            req.dividend_per_share,
            note=req.note,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.patch("/holdings/{ticker}")
async def patch_holding(ticker: str, body: HoldingPatch, db: Session = Depends(get_db)):
    acc = _account(db)
    t = ticker.upper()
    row = ps.get_holding(db, acc.id, t)
    if row is None:
        raise HTTPException(404, f"No holding for {t}")
    if body.shares is not None:
        row.shares = body.shares
    if body.avg_cost is not None:
        row.avg_cost = body.avg_cost
    db.commit()
    return {"ok": True, "ticker": t, "shares": float(row.shares), "avg_cost": float(row.avg_cost)}
