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


class Decision(Base):
    """A recorded investment decision, with the reasoning and the book behind it.

    The portfolio context is stored inline rather than referenced. Weights,
    correlation and concentration all move, so a decision reviewed a year later
    has to be judged against the book as it was when the call was made — not
    against today's, which would make every past decision look like it was taken
    with information nobody had.
    """

    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(16), index=True)  # buy | sell | hold | watch | pass
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open | closed

    conviction: Mapped[int | None] = mapped_column(nullable=True)
    stance: Mapped[str | None] = mapped_column(String(16), nullable=True)
    thesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    proposed_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    proposed_weight_pct: Mapped[float | None] = mapped_column(nullable=True)
    price_at_decision: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)

    # The book as it stood, and what this would have done to it.
    sizing: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    portfolio_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    research_run_uid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    executed: Mapped[bool] = mapped_column(default=False)
    transaction_id: Mapped[int | None] = mapped_column(nullable=True)

    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Membership
#
# The hosted deployment runs `llm_provider=openai` against a paid gateway, so
# the four model-invoking routes bill whoever deployed the site. For a long
# time the only honest setting was to switch them off entirely
# (`llm_endpoints_enabled=False`), which left the best part of the app dark in
# public. These four tables are what lets it come back on: a named member
# carrying a token budget is not an anonymous proxy.
#
# Three properties are load-bearing, and all three are about revocation rather
# than growth. A marginal member here is a recurring charge, not a free signup,
# so this is a spend-authorisation tree and not a referral loop.
#
#   1. Secrets are stored only as SHA-256 hashes. The invite secret lives in
#      the link and the session secret lives in the cookie, and nowhere else,
#      so a dump of the database admits nobody.
#   2. Sessions are rows, not signed cookies. That is the entire reason for the
#      table: revoking a member can then kill their live session in the same
#      transaction. A stateless signed token cannot be withdrawn before it
#      expires, and "revoked but still browsing" is the case that matters.
#   3. `admitted_by` and `Invite.issued_by` are written from the first day even
#      though only the owner issues invites. There is no Alembic in this repo —
#      `init_db()` is `create_all` and nothing else — so a column added once
#      the volume holds real members means hand-written SQL against production.
#
# Datetimes here are **naive UTC**, unlike the `server_default=func.now()`
# columns above. SQLite has no timezone storage, so an aware value is written
# as a naive string anyway and the awareness is silently lost on read; the
# comparisons below (`expires_at > now`) have to be exact, so the convention is
# stated once and applied everywhere rather than left to the dialect. Use
# `hedge_fund.members.service.utcnow()`.


class Member(Base):
    """Someone who has been let in. The label is the owner's own note."""

    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(128))

    #: Explicit rather than inferred from `admitted_by IS NULL`. Overloading
    #: null to also mean "owner" leaves a future grant permission with nothing
    #: to key off.
    is_owner: Mapped[bool] = mapped_column(default=False)

    #: Who let them in. Null means seeded directly by the owner's CLI, which is
    #: every member in v1 — members cannot invite anyone yet.
    admitted_by: Mapped[int | None] = mapped_column(
        ForeignKey("members.id", ondelete="SET NULL"), nullable=True, index=True
    )

    #: Tokens per UTC calendar month, summed across every model call made on
    #: this member's behalf. 0 means no model access at all.
    llm_monthly_token_cap: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sessions: Mapped[list["MemberSession"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )


class Invite(Base):
    """A single-use capability to become a member.

    The row is the invite; the secret that opens it is never stored. Admission
    consumes the row in one UPDATE (see `members.service.consume_invite`)
    rather than a read followed by a write, because SQLAlchemy opens SQLite
    transactions DEFERRED and two simultaneous clicks on a forwarded link would
    otherwise both pass the read.
    """

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    #: The label and cap the minted member will be created with. Carried on the
    #: invite so the owner decides the budget when they hand out the link, not
    #: afterwards.
    label: Mapped[str] = mapped_column(String(128))
    llm_monthly_token_cap: Mapped[int] = mapped_column(default=0)

    #: Whether consuming this invite produces the owner rather than an ordinary
    #: member. Exists so the owner can obtain their own session through the
    #: same door everyone else uses: a CLI cannot set a cookie in a browser, so
    #: without this the owner would need a second, privileged login path, and a
    #: second path is a second thing to get wrong.
    grants_owner: Mapped[bool] = mapped_column(default=False)

    #: Null means minted by the owner's CLI. Populated from day one so turning
    #: member-granted invites on later is a feature flag, not a migration.
    issued_by: Mapped[int | None] = mapped_column(
        ForeignKey("members.id", ondelete="SET NULL"), nullable=True, index=True
    )

    issued_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #: The one direction the invite-to-member link is stored in. A mirrored
    #: `Member.invite_id` would hold the same fact twice, could disagree with
    #: itself, and would make the two tables a mutual foreign-key cycle that
    #: `create_all` only survives by accident of SQLite's CREATE order.
    consumed_by: Mapped[int | None] = mapped_column(
        ForeignKey("members.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MemberSession(Base):
    """One browser, holding one secret, until it expires or is revoked."""

    __tablename__ = "member_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    #: Touched at most hourly, not per request. Every request would be a SQLite
    #: write on a network volume, and the column only has to answer "is this
    #: seat still in use", which an hour resolves fine.
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    member: Mapped["Member"] = relationship(back_populates="sessions")


class LlmUsage(Base):
    """One model call, attributed to whoever caused it.

    Written after the call from the provider's own reported counts, so the
    numbers are measured rather than estimated. Two consequences of recording
    after rather than reserving before, both accepted at this scale: a single
    in-flight call can carry a member past their cap (bounded by one call), and
    a gateway timeout or 5xx can bill without returning counts, so the ledger
    can undercount by the failure rate.

    `cost_usd` is filled only when the gateway reports a cost. There is no
    local price table on purpose — a hardcoded per-model price drifts silently,
    and the rest of this app exists to avoid plausible unverifiable numbers.
    The dollar question is answered by the gateway's own dashboard; this table
    answers the token question, which is the one the cap is denominated in.
    """

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), index=True)

    #: The API route that caused the call, not the model's own name for itself.
    #: A committee run is many calls under one route.
    route: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))

    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
