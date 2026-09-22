"""Seed the demo team for the zero-config first run.

Usage:
    python -m leadgen.scripts.seed_demo

Idempotent — re-running skips what already exists. Creates four
users (password ``demo1234``: owner@/admin@/manager@/sales@demo.local),
the «Отдел продаж (демо)» team, the «Аудит-первый» funnel and ten
leads with a live call queue. Same dataset the one-click demo login
(``/api/v1/auth/demo``) provisions on first use.

DEMO data — never run against the production database.
"""

from __future__ import annotations

import asyncio

from leadgen.core.services.demo_data import DEMO_USERS, ensure_demo_data
from leadgen.db.session import dispose_engine, get_session


async def _main() -> int:
    try:
        async with get_session() as session:
            await ensure_demo_data(session)
        print("Демо-данные готовы. Логины (пароль demo1234):")
        for _uid, email, name, role in DEMO_USERS:
            print(f"  {email:<22} {name:<7} {role}")
        return 0
    finally:
        await dispose_engine()


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
