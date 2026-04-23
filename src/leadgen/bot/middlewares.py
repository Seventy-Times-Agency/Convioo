from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import async_sessionmaker

from leadgen.config import get_settings
from leadgen.db.models import User


class DbSessionMiddleware(BaseMiddleware):
    """Opens a DB session per update and upserts the user record.

    Injects ``session: AsyncSession`` and ``user: User`` into handler kwargs.
    """

    def __init__(self, session_pool: async_sessionmaker) -> None:
        self.session_pool = session_pool

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_pool() as session:
            data["session"] = session

            tg_user: TgUser | None = data.get("event_from_user")
            if tg_user is not None:
                user = await session.get(User, tg_user.id)
                if user is None:
                    user = User(
                        id=tg_user.id,
                        username=tg_user.username,
                        first_name=tg_user.first_name,
                        language_code=tg_user.language_code,
                        queries_limit=get_settings().default_queries_limit,
                    )
                    session.add(user)
                    await session.commit()
                data["user"] = user

            return await handler(event, data)
