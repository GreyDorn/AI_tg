from typing import Callable, Awaitable, Any
from datetime import datetime
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from config import resolve_model_key
from bot.i18n import resolve_lang
from db.repository import SessionFactory, get_or_create_user, claim_daily_credits, update_user_model


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
                language_code=tg_user.language_code,
            )

            if not is_new:
                now = datetime.now()
                if not user.last_active_date or user.last_active_date.date() != now.date():
                    user.last_active_date = now
                    await session.commit()
                await claim_daily_credits(session, tg_user.id)
                await session.refresh(user)

            resolved_model = resolve_model_key(user.current_model)
            if resolved_model != user.current_model:
                user.current_model = resolved_model
                await update_user_model(session, user.id, resolved_model)

            data["db_session"] = session
            data["db_user"] = user
            data["is_new_user"] = is_new
            data["lang"] = resolve_lang(user)
            return await handler(event, data)
