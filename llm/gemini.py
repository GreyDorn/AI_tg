import logging
from typing import AsyncIterator
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, MAX_CONTEXT_CHARS
from db.models import Message
from llm.base import BaseLLM
from llm.groq_llm import GroqLLM

logger = logging.getLogger(__name__)

GEMINI_FALLBACK_MODEL = "llama-3.3-70b-versatile"


def _is_retryable_error(exc: Exception) -> bool:
    error_str = str(exc).lower()
    return (
        "503" in str(exc)
        or "429" in str(exc)
        or "quota" in error_str
        or "resource_exhausted" in error_str
        or "unavailable" in error_str
        or "overloaded" in error_str
    )


class GeminiLLM(BaseLLM):
    def __init__(self) -> None:
        self.client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
        self._groq = GroqLLM()

    async def stream(
        self, messages: list[Message], model_id: str, disable_thinking: bool = False
    ) -> AsyncIterator[str]:
        if self.client:
            try:
                async for chunk in self._stream_gemini(messages, model_id):
                    yield chunk
                return
            except Exception as exc:
                if _is_retryable_error(exc):
                    logger.warning("Gemini failed model=%s, using Groq fallback: %s", model_id, exc)
                else:
                    raise

        async for chunk in self._groq.stream(messages, GEMINI_FALLBACK_MODEL, disable_thinking):
            yield chunk

    async def _stream_gemini(
        self, messages: list[Message], model_id: str
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

        while total_chars > MAX_CONTEXT_CHARS and len(messages) > 1:
            total_chars -= len(messages[0].content)
            messages = messages[1:]

        for msg in messages:
            role = "user" if msg.role == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg.content)]))
        return contents
