import logging
from typing import Callable, Awaitable, Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from db.repository import SessionFactory, try_claim_event

logger = logging.getLogger(__name__)


class IdempotencyMiddleware(BaseMiddleware):
    """Skip duplicate Telegram updates (same update_id) using SQLite."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update: Update | None = data.get("event_update")
        if not update or update.update_id is None:
            return await handler(event, data)

        event_key = f"tg:{update.update_id}"
        async with SessionFactory() as session:
            if not await try_claim_event(session, event_key, "telegram"):
                logger.debug("Duplicate Telegram update %s", update.update_id)
                return

        data["idempotency_key"] = event_key
        return await handler(event, data)
