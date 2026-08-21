"""ORM models — single-account portfolio (multi-row holdings)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
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

    holdings: Mapped[list["Holding"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    corporate_actions: Mapped[list["CorporateAction"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
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
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    txn_type: Mapped[str] = mapped_column(String(24), index=True)
    ticker: Mapped[str | None] = mapped_column(String(32), nullable=True)
    shares: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    price_per_share: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    fee: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    cash_delta: Mapped[Decimal] = mapped_column(Numeric(24, 8))  # signed: negative = cash out
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    account: Mapped["Account"] = relationship(back_populates="transactions")


class CorporateAction(Base):
    __tablename__ = "corporate_actions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    action_type: Mapped[str] = mapped_column(String(24))
    ex_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    split_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8), nullable=True
    )  # e.g. 4 for 4:1
    dividend_per_share: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped["Account"] = relationship(back_populates="corporate_actions")


class ResearchSnapshot(Base):
    """Immutable market-data bundle an analysis was run against.

    Content-addressed and deduplicated: re-running the same ticker against
    unchanged data reuses the row rather than storing the payload twice. This is
    the object a replay reads, so a past run can be reproduced exactly instead of
    re-fetched against whatever the providers say today.
    """

    __tablename__ = "research_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    runs: Mapped[list["ResearchRun"]] = relationship(back_populates="snapshot")


class ResearchRun(Base):
    """One executed analysis, with everything needed to replay or diff it."""

    __tablename__ = "research_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_uid: Mapped[str] = mapped_column(String(36), unique=True, index=True)

    # Identity of the determined inputs. Two runs sharing run_key should agree;
    # when they do not, the divergence is the signal.
    run_key: Mapped[str] = mapped_column(String(64), index=True)

    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    snapshot_sha256: Mapped[str] = mapped_column(String(64), index=True)

    ticker: Mapped[str] = mapped_column(String(32), index=True)
    mode: Mapped[str] = mapped_column(String(24), index=True)  # single | persona | committee | plan
    persona_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    committee_personas: Mapped[list | None] = mapped_column(JSON, nullable=True)

    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prompt_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)

    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evaluation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verification: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    committee_detail: Mapped[list | None] = mapped_column(JSON, nullable=True)
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    methodology_note_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    replay_of: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    snapshot: Mapped["ResearchSnapshot | None"] = relationship(back_populates="runs")


class MethodologyNote(Base):
    """A durable correction of *method*, learned from a run and reused later.

    Only portable method text is stored — never chat history, data, or the
    numbers from the run that prompted it. That keeps the corpus reviewable by a
    human and safe to carry between tickers, which is the whole point: the
    artifact accumulating value is a body of methodology, not a pile of prompts.
    """

    __tablename__ = "methodology_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    note: Mapped[str] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    scope_ticker: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    scope_persona: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_run_uid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active: Mapped[bool] = mapped_column(default=True, index=True)
    times_applied: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Experiment(Base):
    """One autoresearch hypothesis and its verdict.

    Discarded experiments are kept deliberately. The count of what was tried is
    what makes the surviving result interpretable — a Sharpe of 1.4 means
    something different as the first idea than as the best of two hundred.
    """

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_tag: Mapped[str] = mapped_column(String(64), index=True)
    seq: Mapped[int] = mapped_column(index=True)

    ticker: Mapped[str] = mapped_column(String(32), index=True)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_baseline: Mapped[bool] = mapped_column(default=False)
    kept: Mapped[bool] = mapped_column(default=False, index=True)
    verdict: Mapped[str] = mapped_column(String(24), index=True)  # kept | discarded | error

    in_sample: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    out_of_sample: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    baseline_out_of_sample: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    primary_metric: Mapped[float | None] = mapped_column(nullable=True, index=True)
    edge_vs_baseline: Mapped[float | None] = mapped_column(nullable=True)
    degradation: Mapped[float | None] = mapped_column(nullable=True)
    hurdle: Mapped[float | None] = mapped_column(nullable=True)
    overfit_flag: Mapped[bool] = mapped_column(default=False)

    notes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
