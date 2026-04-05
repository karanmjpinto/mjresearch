"""ORM models — single-account portfolio (multi-row holdings)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hedge_fund.db.session import Base


class TxnType(StrEnum):
    BUY = "buy"
    SELL = "sell"
    CASH_DEPOSIT = "cash_deposit"
    CASH_WITHDRAW = "cash_withdraw"
    DIVIDEND = "dividend"
    SPLIT = "split"
    SEED = "seed"


class CorporateActionType(StrEnum):
    STOCK_SPLIT = "stock_split"
    CASH_DIVIDEND = "cash_dividend"
    MERGER = "merger"
    SPINOFF = "spinoff"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), default="Primary")
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    benchmark: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    holdings: Mapped[list["Holding"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    corporate_actions: Mapped[list["CorporateAction"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    shares: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    account: Mapped["Account"] = relationship(back_populates="holdings")

    __table_args__ = (UniqueConstraint("account_id", "ticker", name="uq_holding_account_ticker"),)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    txn_type: Mapped[str] = mapped_column(String(24), index=True)
    ticker: Mapped[str | None] = mapped_column(String(32), nullable=True)
    shares: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    price_per_share: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    fee: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    cash_delta: Mapped[Decimal] = mapped_column(Numeric(24, 8))  # signed: negative = cash out
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped["Account"] = relationship(back_populates="transactions")


class CorporateAction(Base):
    __tablename__ = "corporate_actions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    action_type: Mapped[str] = mapped_column(String(24))
    ex_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    split_ratio: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)  # e.g. 4 for 4:1
    dividend_per_share: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped["Account"] = relationship(back_populates="corporate_actions")
