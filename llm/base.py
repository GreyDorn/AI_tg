from abc import ABC, abstractmethod
from typing import AsyncIterator
from db.models import Message


class BaseLLM(ABC):
    """Базовый класс для всех LLM провайдеров."""

    @abstractmethod
    async def stream(
        self, messages: list[Message], model_id: str, disable_thinking: bool = False
    ) -> AsyncIterator[str]:
        """Стриминг ответа по частям."""
        ...

    def _build_history(self, messages: list[Message]) -> list[dict]:
        """Конвертирует сообщения БД в формат [{role, content}]."""
        return [{"role": m.role, "content": m.content} for m in messages]
