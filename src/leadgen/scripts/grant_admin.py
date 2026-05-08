"""Toggle the ``users.is_admin`` flag from the command line.

Usage:
    python -m leadgen.scripts.grant_admin <email>            # grants admin
    python -m leadgen.scripts.grant_admin <email> --revoke   # revokes admin

Reads ``DATABASE_URL`` from the environment via the standard config loader,
so it works the same locally and on Railway (``railway run python -m
leadgen.scripts.grant_admin you@example.com``).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select, update

from leadgen.db.models import User
from leadgen.db.session import dispose_engine, get_session


async def _run(email: str, revoke: bool) -> int:
    target = email.strip().lower()
    if not target:
        print("error: empty email", file=sys.stderr)
        return 2

    async with get_session() as session:
        existing = (
            await session.execute(select(User).where(User.email == target))
        ).scalar_one_or_none()

        if existing is None:
            print(f"error: no user with email {target!r}", file=sys.stderr)
            return 1

        new_value = not revoke
        if bool(existing.is_admin) == new_value:
            state = "admin" if new_value else "not admin"
            print(f"{target} is already {state}; nothing to do.")
            return 0

        await session.execute(
            update(User).where(User.id == existing.id).values(is_admin=new_value)
        )
        await session.commit()

    verb = "granted" if new_value else "revoked"
    print(f"{verb} admin for {target}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant or revoke platform admin.")
    parser.add_argument("email", help="user email")
    parser.add_argument(
        "--revoke", action="store_true", help="revoke admin instead of granting"
    )
    args = parser.parse_args()

    try:
        code = asyncio.run(_run(args.email, args.revoke))
    finally:
        try:
            asyncio.run(dispose_engine())
        except Exception:
            pass
    sys.exit(code)


if __name__ == "__main__":
    main()
