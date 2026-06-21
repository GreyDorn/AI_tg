import time
from collections import defaultdict, deque
from typing import Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from config import RATE_LIMIT_MESSAGES, RATE_LIMIT_WINDOW


class RateLimitMiddleware(BaseMiddleware):
    """Ограничивает количество сообщений от одного пользователя."""

    def __init__(self):
        # user_id -> deque с временными метками запросов
        self._history: dict[int, deque] = defaultdict(lambda: deque())

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if not tg_user:
            return await handler(event, data)

        # Применяем только к текстовым сообщениям (не командам и не кнопкам)
        message = data.get("event_update")
        raw = getattr(event, "message", None)
        if not isinstance(raw, Message) or not raw.text or raw.text.startswith("/"):
            return await handler(event, data)

        now = time.monotonic()
        user_id = tg_user.id
        history = self._history[user_id]

        # Удаляем старые записи вне окна
        while history and now - history[0] > RATE_LIMIT_WINDOW:
            history.popleft()

        if len(history) >= RATE_LIMIT_MESSAGES:
            wait_seconds = int(RATE_LIMIT_WINDOW - (now - history[0])) + 1
            await raw.answer(
                f"⏱ <b>Too many requests</b>\n\n"
                f"Please wait <b>{wait_seconds} sec.</b> before sending the next message.",
                parse_mode="HTML",
            )
            return

        history.append(now)
        return await handler(event, data)
