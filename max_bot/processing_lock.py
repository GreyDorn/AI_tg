"""Prevent parallel LLM requests from the same MAX user."""

from __future__ import annotations

from max_bot.api import send_message

_processing: set[int] = set()
WAIT_TEXT = "⏳ Подожди, я ещё обрабатываю предыдущий запрос..."


async def try_acquire(user_id: int) -> bool:
    if user_id in _processing:
        await send_message(user_id=user_id, text=WAIT_TEXT)
        return False
    _processing.add(user_id)
    return True


def release(user_id: int) -> None:
    _processing.discard(user_id)
