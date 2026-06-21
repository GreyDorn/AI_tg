from typing import Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from db.repository import SessionFactory, get_or_create_user, claim_daily_credits


class UserMiddleware(BaseMiddleware):
    """
    Регистрирует пользователя при первом обращении,
    начисляет ежедневные запросы, проверяет истечение подписки.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if not tg_user:
            return await handler(event, data)

        referred_by: int | None = None
        if isinstance(event, Update) and event.message and event.message.text:
            parts = event.message.text.split(maxsplit=1)
            if len(parts) == 2 and parts[0] == "/start" and parts[1].startswith("ref"):
                try:
                    referred_by = int(parts[1][3:])
                except ValueError:
                    pass

        async with SessionFactory() as session:
            user, is_new = await get_or_create_user(
                session,
                user_id=tg_user.id,
                full_name=tg_user.full_name,
                username=tg_user.username,
                referred_by=referred_by,
            )

            if not is_new:
                await claim_daily_credits(session, tg_user.id)
                await session.refresh(user)

            data["db_session"] = session
            data["db_user"] = user
            return await handler(event, data)
