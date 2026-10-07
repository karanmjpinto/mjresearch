"""Membership operations. No HTTP, no FastAPI — just the database.

Everything that decides who is in, what they may spend, and how to take it
away. The API layer and the CLI are both thin wrappers over this.

Two conventions, stated once:

- **Datetimes are naive UTC.** SQLite stores no timezone, so an aware value is
  written as a naive string and the awareness is lost on read. Every comparison
  in here (`expires_at > now`) has to be exact, so the convention is explicit
  rather than left to the dialect. Use `utcnow()`.
- **Secrets are never stored.** `mint_invite` and `open_session` return the
  secret to the caller once and persist only `sha256(secret)`. There is no way
  to recover one, which is the point: a database dump admits nobody.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from hedge_fund.db.models import Invite, LlmUsage, Member, MemberSession
from hedge_fund.settings import settings

#: Length in bytes before base64, so ~43 URL-safe characters. Far past the
#: point where guessing matters, but the join endpoint is rate-limited anyway
#: because entropy is not a substitute for not being an oracle.
_TOKEN_BYTES = 32


def utcnow() -> datetime:
    """Now, as naive UTC. The one clock this module uses."""
    return datetime.now(UTC).replace(tzinfo=None)


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def month_start(now: datetime | None = None) -> datetime:
    """First instant of the current UTC calendar month.

    Month-to-date needs exactly one definition because it is the number the
    budget refusal fires on. A rolling 30-day window would be defensible too,
    but then "this month" in the UI and "this month" in the check would drift
    apart at the boundary and nobody would be able to explain the 429.
    """
    ref = now or utcnow()
    return ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Invites


@dataclass(frozen=True)
class MintedInvite:
    invite: Invite
    #: Returned once. Not recoverable afterwards.
    secret: str


def mint_invite(
    db: Session,
    *,
    label: str,
    token_cap: int | None = None,
    expires_in: timedelta = timedelta(days=7),
    issued_by: int | None = None,
    grants_owner: bool = False,
) -> MintedInvite:
    """Create a single-use invite and return its secret once."""
    secret = secrets.token_urlsafe(_TOKEN_BYTES)
    now = utcnow()
    invite = Invite(
        token_hash=_hash(secret),
        label=label,
        llm_monthly_token_cap=(
            settings.member_default_token_cap if token_cap is None else token_cap
        ),
        grants_owner=grants_owner,
        issued_by=issued_by,
        issued_at=now,
        expires_at=now + expires_in,
    )
    db.add(invite)
    db.flush()
    return MintedInvite(invite=invite, secret=secret)


class InviteRejected(Exception):
    """An invite could not be used, with a reason the holder can act on.

    The reason is deliberately specific. "Invalid" tells someone holding a
    forwarded link nothing useful, and the four cases have different remedies:
    ask for a new one (used, expired), you were never the intended recipient
    (unknown), or the owner took it back and asking again may be the wrong move
    (withdrawn).
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        #: One of: used, expired, withdrawn, unknown.
        self.reason = reason
        self.message = message


def consume_invite(db: Session, secret: str) -> tuple[Member, str]:
    """Spend an invite, create the member, and open their first session.

    Admission is a single conditional UPDATE rather than a read followed by a
    write. SQLAlchemy opens SQLite transactions DEFERRED, so two simultaneous
    clicks on a forwarded link would both pass a `SELECT ... WHERE consumed_at
    IS NULL` and both go on to create a member. Letting the database decide the
    winner — by requiring `rowcount == 1` on an UPDATE whose WHERE clause
    includes the unconsumed condition — makes admission at-most-once without a
    lock.

    Returns the new member and their session secret. Raises `InviteRejected`
    with a usable reason if the invite cannot be spent.
    """
    now = utcnow()
    token_hash = _hash(secret)

    claimed = db.execute(
        update(Invite)
        .where(
            Invite.token_hash == token_hash,
            Invite.consumed_at.is_(None),
            Invite.revoked_at.is_(None),
            Invite.expires_at > now,
        )
        .values(consumed_at=now)
    )

    if claimed.rowcount != 1:
        # The UPDATE matched nothing. Read the row — if it exists at all — to
        # say which of the three reasons it was. This read is safe precisely
        # because the write already failed: there is no race left to lose.
        row = db.execute(select(Invite).where(Invite.token_hash == token_hash)).scalar_one_or_none()
        db.rollback()
        if row is None:
            raise InviteRejected(
                "unknown",
                "That is not an invite to this site. If someone forwarded you a "
                "link, ask them for one of their own.",
            )
        if row.consumed_at is not None:
            raise InviteRejected(
                "used",
                "That invite has already been used. Each one opens once, so if "
                "this was meant for you, ask for a fresh link.",
            )
        if row.revoked_at is not None:
            # Its own reason, not "used". The screen maps reason to a heading,
            # and "already been opened" over a body saying it was withdrawn
            # contradicts itself — then tells the holder to ask for a fresh
            # link for an invite the owner deliberately took back.
            raise InviteRejected(
                "withdrawn",
                "That invite was withdrawn before it was used. Whoever sent it "
                "took it back, so asking for another may not be the next step.",
            )
        raise InviteRejected(
            "expired",
            "That invite has expired. Ask for a new one — they are short-lived on purpose.",
        )

    invite = db.execute(select(Invite).where(Invite.token_hash == token_hash)).scalar_one()

    member = Member(
        label=invite.label,
        is_owner=invite.grants_owner,
        admitted_by=invite.issued_by,
        llm_monthly_token_cap=invite.llm_monthly_token_cap,
        created_at=now,
    )
    db.add(member)
    db.flush()

    invite.consumed_by = member.id
    session_secret = open_session(db, member.id)
    db.commit()
    return member, session_secret


def revoke_invite(db: Session, invite_id: int) -> bool:
    """Withdraw an unused invite. Returns False if there was no such invite."""
    invite = db.get(Invite, invite_id)
    if invite is None:
        return False
    if invite.revoked_at is None:
        invite.revoked_at = utcnow()
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Sessions


def open_session(db: Session, member_id: int) -> str:
    """Start a session for a member and return its secret once."""
    secret = secrets.token_urlsafe(_TOKEN_BYTES)
    now = utcnow()
    db.add(
        MemberSession(
            token_hash=_hash(secret),
            member_id=member_id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=settings.member_session_days),
        )
    )
    db.flush()
    return secret


#: How stale `last_seen_at` is allowed to get before it is worth a write.
_TOUCH_AFTER = timedelta(hours=1)


def resolve_session(db: Session, secret: str | None) -> Member | None:
    """The member this cookie belongs to, or None.

    None covers every failure identically — no cookie, unknown cookie, expired
    session, revoked session, revoked member — because the caller's response is
    the same in all five cases and distinguishing them for the client would
    leak whether a given secret was ever real.
    """
    if not secret:
        return None

    now = utcnow()
    row = db.execute(
        select(MemberSession, Member)
        .join(Member, Member.id == MemberSession.member_id)
        .where(
            MemberSession.token_hash == _hash(secret),
            MemberSession.revoked_at.is_(None),
            MemberSession.expires_at > now,
            Member.revoked_at.is_(None),
        )
    ).one_or_none()

    if row is None:
        return None

    session, member = row
    if now - session.last_seen_at > _TOUCH_AFTER:
        session.last_seen_at = now
        db.commit()
    return member


def close_session(db: Session, secret: str | None) -> None:
    """Revoke the session this cookie names. Silent if there isn't one."""
    if not secret:
        return
    db.execute(
        update(MemberSession)
        .where(MemberSession.token_hash == _hash(secret), MemberSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    db.commit()


def revoke_member(db: Session, member_id: int) -> bool:
    """Revoke a member and kill their live sessions in one transaction.

    The second half is the whole reason sessions are rows. A signed cookie
    cannot be withdrawn before it expires, so a revoked member would keep
    browsing — and keep spending — from an already-open tab until it did.
    """
    member = db.get(Member, member_id)
    if member is None:
        return False
    now = utcnow()
    if member.revoked_at is None:
        member.revoked_at = now
    db.execute(
        update(MemberSession)
        .where(MemberSession.member_id == member_id, MemberSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Spend


def tokens_this_month(db: Session, member_id: int) -> int:
    """Prompt + completion tokens for this member since the month began."""
    total = db.execute(
        select(
            func.coalesce(func.sum(LlmUsage.prompt_tokens + LlmUsage.completion_tokens), 0)
        ).where(
            LlmUsage.member_id == member_id,
            LlmUsage.created_at >= month_start(),
        )
    ).scalar_one()
    return int(total or 0)


@dataclass(frozen=True)
class Spend:
    tokens: int
    cap: int

    @property
    def exhausted(self) -> bool:
        # A cap of 0 means no model access, which is exhausted by definition —
        # and is the default, so an invite minted without a cap cannot spend.
        return self.tokens >= self.cap

    @property
    def fraction(self) -> float:
        if self.cap <= 0:
            return 1.0
        return min(self.tokens / self.cap, 1.0)


def spend_for(db: Session, member: Member) -> Spend:
    return Spend(tokens=tokens_this_month(db, member.id), cap=member.llm_monthly_token_cap)


def record_usage(
    db: Session,
    *,
    member_id: int,
    route: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: object | None = None,
) -> None:
    """Append one metered model call."""
    db.add(
        LlmUsage(
            member_id=member_id,
            route=route,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            created_at=utcnow(),
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# Seeding


def ensure_owner(db: Session, label: str = "owner", token_cap: int | None = None) -> Member:
    """The owner's own member row, created directly and without a browser.

    Idempotent. Used by tests and by any seeding that has no browser to put a
    cookie in; the CLI's `own` command goes through an owner-granting invite
    instead, so the owner arrives through the same door as everyone else.
    """
    existing = db.execute(select(Member).where(Member.is_owner.is_(True))).scalars().first()
    if existing is not None:
        return existing
    member = Member(
        label=label,
        is_owner=True,
        llm_monthly_token_cap=(
            settings.member_default_token_cap if token_cap is None else token_cap
        ),
        created_at=utcnow(),
    )
    db.add(member)
    db.commit()
    return member
