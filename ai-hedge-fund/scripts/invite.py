#!/usr/bin/env python
"""Hand out, inspect and withdraw invites.

The owner is the only person who issues invites, so this is a CLI rather than
an admin screen — a web UI for one user is work that buys nothing, and a CLI
cannot be reached from the internet at all.

    uv run python scripts/invite.py mint --label "Jude" --cap-tokens 200000
    uv run python scripts/invite.py list
    uv run python scripts/invite.py revoke member 3
    uv run python scripts/invite.py revoke invite 7

`mint` prints the link once. The secret is hashed before it is stored and
cannot be recovered, so if you lose the output, withdraw that invite and mint
another.

`revoke` takes a kind as well as an id on purpose. Members and invites are both
numbered from 1, so `revoke 7` is ambiguous in a way that would eventually
revoke the wrong thing.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from hedge_fund.db.models import Invite, Member, MemberSession  # noqa: E402
from hedge_fund.db.session import SessionLocal, init_db  # noqa: E402
from hedge_fund.members import service  # noqa: E402
from hedge_fund.settings import settings  # noqa: E402

_DURATION = re.compile(r"^(\d+)([dh])$")


def parse_duration(text: str) -> timedelta:
    match = _DURATION.match(text.strip().lower())
    if not match:
        raise argparse.ArgumentTypeError(f"expected something like 7d or 48h, got {text!r}")
    amount, unit = int(match.group(1)), match.group(2)
    return timedelta(days=amount) if unit == "d" else timedelta(hours=amount)


def describe(delta: timedelta) -> str:
    """`7d` back out as "7 days", so the confirmation reads like the flag."""
    hours = int(delta.total_seconds() // 3600)
    if hours % 24 == 0 and hours >= 24:
        days = hours // 24
        return f"{days} day{'s' if days != 1 else ''}"
    return f"{hours} hour{'s' if hours != 1 else ''}"


def base_url() -> str:
    """Where to point the invite link.

    `public_base_url` if set, else `FRONTEND_URL`, else localhost — in that
    order, because a link printed with the wrong origin is a link that silently
    does not work for the person you sent it to.
    """
    import os

    configured = settings.public_base_url or os.environ.get("FRONTEND_URL")
    return (configured or "http://localhost:5173").rstrip("/")


def cmd_mint(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        minted = service.mint_invite(
            db,
            label=args.label,
            token_cap=args.cap_tokens,
            expires_in=args.expires,
        )
        db.commit()
        # The fragment, not the path. A path would be sent to the server and
        # land in uvicorn, Railway and Cloudflare access logs, in browser
        # history, and in any outbound Referer header. A fragment is never
        # transmitted at all.
        link = f"{base_url()}/join#{minted.secret}"
        print()
        print(f"  invite {minted.invite.id} for {args.label!r}")
        print(f"  {args.cap_tokens:,} tokens/month, expires in {describe(args.expires)}")
        print()
        print(f"  {link}")
        print()
        print("  Printed once. The secret is not stored and cannot be recovered.")
        print()
        return 0
    finally:
        db.close()


def cmd_list(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        members = db.execute(select(Member).order_by(Member.id)).scalars().all()
        if not members:
            print("No members yet. Mint an invite, or seed yourself with `own`.")
        else:
            labels = {m.id: m.label for m in members}
            print()
            print(
                f"  {'id':>3}  {'label':<24} {'admitted by':<14} "
                f"{'tokens / cap':>20}  {'last seen':<17} state"
            )
            for m in members:
                spend = service.spend_for(db, m)
                last = db.execute(
                    select(MemberSession.last_seen_at)
                    .where(MemberSession.member_id == m.id)
                    .order_by(MemberSession.last_seen_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
                by = (
                    "owner (seed)"
                    if m.admitted_by is None
                    else labels.get(m.admitted_by, str(m.admitted_by))
                )
                state = "revoked" if m.revoked_at else ("owner" if m.is_owner else "active")
                usage = f"{spend.tokens:,} / {spend.cap:,}"
                seen = last.strftime("%Y-%m-%d %H:%M") if last else "never"
                print(
                    f"  {m.id:>3}  {m.label[:24]:<24} {by[:14]:<14} {usage:>20}  {seen:<17} {state}"
                )
            print()
            print("  Tokens are month-to-date (UTC calendar month). Dollars are")
            print("  the gateway's own number — this ledger counts tokens, which")
            print("  is what the cap is denominated in.")
            print()

        pending = (
            db.execute(
                select(Invite)
                .where(Invite.consumed_at.is_(None), Invite.revoked_at.is_(None))
                .order_by(Invite.id)
            )
            .scalars()
            .all()
        )
        now = service.utcnow()
        live = [i for i in pending if i.expires_at > now]
        if live:
            print(f"  {len(live)} invite(s) outstanding:")
            for i in live:
                hours = int((i.expires_at - now).total_seconds() // 3600)
                print(
                    f"    invite {i.id}: {i.label!r}, "
                    f"{i.llm_monthly_token_cap:,} tokens/month, {hours}h left"
                )
            print()
        return 0
    finally:
        db.close()


def cmd_revoke(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        if args.kind == "member":
            if not service.revoke_member(db, args.id):
                print(f"No member {args.id}.", file=sys.stderr)
                return 1
            # The second half is why sessions are rows: an already-open tab
            # stops working now, rather than whenever its cookie expires.
            print(f"Member {args.id} revoked, and their live sessions closed.")
        else:
            if not service.revoke_invite(db, args.id):
                print(f"No invite {args.id}.", file=sys.stderr)
                return 1
            print(f"Invite {args.id} withdrawn. The link no longer opens.")
        return 0
    finally:
        db.close()


def cmd_own(args: argparse.Namespace) -> int:
    """Mint the owner's own invite.

    Not a direct session: a CLI cannot set a cookie in a browser, so the owner
    gets a link and clicks it like everyone else. Consuming it sets `is_owner`
    on the member it creates, which is the flag a future grant permission will
    key off.
    """
    db = SessionLocal()
    try:
        minted = service.mint_invite(
            db,
            label=args.label,
            token_cap=args.cap_tokens,
            expires_in=args.expires,
            grants_owner=True,
        )
        db.commit()
        print()
        print(f"  owner invite {minted.invite.id} for {args.label!r}")
        print(f"  {args.cap_tokens:,} tokens/month, expires in {describe(args.expires)}")
        print()
        print(f"  {base_url()}/join#{minted.secret}")
        print()
        print("  Click it in the browser you want to be signed in to.")
        print("  Printed once. The secret is not stored and cannot be recovered.")
        print()
        return 0
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    mint = sub.add_parser("mint", help="create a single-use invite link")
    mint.add_argument("--label", required=True, help="your own note, e.g. 'Jude'")
    mint.add_argument(
        "--cap-tokens",
        type=int,
        default=settings.member_default_token_cap,
        help=f"tokens per UTC month (default {settings.member_default_token_cap:,})",
    )
    mint.add_argument("--expires", type=parse_duration, default=timedelta(days=7))
    mint.set_defaults(func=cmd_mint)

    listing = sub.add_parser("list", help="members, spend and outstanding invites")
    listing.set_defaults(func=cmd_list)

    revoke = sub.add_parser("revoke", help="withdraw a member or an invite")
    revoke.add_argument("kind", choices=["member", "invite"])
    revoke.add_argument("id", type=int)
    revoke.set_defaults(func=cmd_revoke)

    own = sub.add_parser("own", help="seed the owner's own member row and session")
    own.add_argument("--label", default="owner")
    own.add_argument("--cap-tokens", type=int, default=settings.member_default_token_cap)
    own.add_argument("--expires", type=parse_duration, default=timedelta(days=7))
    own.set_defaults(func=cmd_own)

    args = parser.parse_args(argv)
    init_db()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
