from typing import AsyncIterator
from groq import AsyncGroq
from config import GROQ_API_KEY, MAX_CONTEXT_CHARS
from db.models import Message
from llm.base import BaseLLM


class GroqLLM(BaseLLM):
    def __init__(self):
        self.client = AsyncGroq(api_key=GROQ_API_KEY)

    async def stream(
        self, messages: list[Message], model_id: str, disable_thinking: bool = False
    ) -> AsyncIterator[str]:
        history = self._build_history(messages)
        history = self._trim_context(history)

        stream = await self.client.chat.completions.create(
            model=model_id,
            messages=history,
            stream=True,
            max_tokens=4096,
        )

        in_think = False
        finish_reason = None
        async for chunk in stream:
            choice = chunk.choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = choice.delta.content
            if delta:
                clean, in_think = self._filter_thinking(delta, in_think)
                if clean:
                    yield clean

        if finish_reason == "length":
            yield "\n\n⚠️ _Ответ обрезан — достигнут лимит токенов. Попроси продолжить._"

    @staticmethod
    def _filter_thinking(text: str, in_think: bool) -> tuple[str, bool]:
        """Фильтрует блоки <think>...</think> из текста."""
        result = ""
        i = 0
        while i < len(text):
            if not in_think:
                start = text.find("<think>", i)
                if start == -1:
                    result += text[i:]
                    break
                result += text[i:start]
                in_think = True
                i = start + 7
            else:
                end = text.find("</think>", i)
                if end == -1:
                    break
                in_think = False
                i = end + 8
        return result, in_think

    def _trim_context(self, history: list[dict]) -> list[dict]:
        total = sum(len(m["content"]) for m in history)
        while total > MAX_CONTEXT_CHARS and len(history) > 1:
            removed = history.pop(0)
            total -= len(removed["content"])
        return history
