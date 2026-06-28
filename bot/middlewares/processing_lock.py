from typing import Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from bot.i18n import resolve_lang, t


class ProcessingLockMiddleware(BaseMiddleware):
    """
    Предотвращает параллельную обработку сообщений одного пользователя.
    Пока идёт LLM-запрос — новые сообщения игнорируются.
    """

    def __init__(self):
        self._processing: set[int] = set()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if not tg_user:
            return await handler(event, data)

        # Применяем только к обычным текстовым сообщениям (не командам)
        raw = getattr(event, "message", None)
        is_chat_message = (
            isinstance(raw, Message)
            and raw.text
            and not raw.text.startswith("/")
        )

        if not is_chat_message:
            return await handler(event, data)

        user_id = tg_user.id

        if user_id in self._processing:
            lang = resolve_lang(tg_user)
            await raw.answer(t("processing_wait", lang))
            return

        self._processing.add(user_id)
        try:
            return await handler(event, data)
        finally:
            self._processing.discard(user_id)
