from typing import AsyncIterator
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, MAX_CONTEXT_CHARS
from db.models import Message
from llm.base import BaseLLM


class GeminiLLM(BaseLLM):
    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    async def stream(
        self, messages: list[Message], model_id: str, disable_thinking: bool = False
    ) -> AsyncIterator[str]:
        contents = self._build_contents(messages)

        async for chunk in await self.client.aio.models.generate_content_stream(
            model=model_id,
            contents=contents,
        ):
            if chunk.text:
                yield chunk.text

    def _build_contents(self, messages: list[Message]) -> list[types.Content]:
        contents = []
        total_chars = sum(len(m.content) for m in messages)

        # Обрезаем контекст если слишком длинный
        while total_chars > MAX_CONTEXT_CHARS and len(messages) > 1:
            total_chars -= len(messages[0].content)
            messages = messages[1:]

        for msg in messages:
            role = "user" if msg.role == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg.content)]))
        return contents
