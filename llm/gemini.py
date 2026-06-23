import logging
from typing import AsyncIterator
from google import genai
from google.genai import types
from config import GEMINI_API_KEY
from db.models import Message
from llm.base import BaseLLM
from llm.groq_llm import GroqLLM
from llm.chat_context import prepare_chat_history

logger = logging.getLogger(__name__)

GEMINI_FALLBACK_MODEL = "llama-3.3-70b-versatile"
VISION_UNAVAILABLE_MSG = "Photo analysis is not available (Gemini API key is missing)."


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
        self,
        messages: list[Message],
        model_id: str,
        disable_thinking: bool = False,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        if self.client:
            try:
                async for chunk in self._stream_gemini(messages, model_id, system_prompt):
                    yield chunk
                return
            except Exception as exc:
                if _is_retryable_error(exc):
                    logger.warning("Gemini failed model=%s, using Groq fallback: %s", model_id, exc)
                else:
                    raise

        async for chunk in self._groq.stream(
            messages, GEMINI_FALLBACK_MODEL, disable_thinking, system_prompt=system_prompt
        ):
            yield chunk

    async def _stream_gemini(
        self,
        messages: list[Message],
        model_id: str,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        history = prepare_chat_history(messages, system_prompt=system_prompt)
        system_instruction = None
        body = history
        if body and body[0].get("role") == "system":
            system_instruction = body[0]["content"]
            body = body[1:]

        contents = [
            types.Content(
                role="user" if msg["role"] == "user" else "model",
                parts=[types.Part(text=msg["content"])],
            )
            for msg in body
        ]
        config = (
            types.GenerateContentConfig(system_instruction=system_instruction)
            if system_instruction
            else None
        )
        async for chunk in await self.client.aio.models.generate_content_stream(
            model=model_id,
            contents=contents,
            config=config,
        ):
            if chunk.text:
                yield chunk.text

    async def stream_vision(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        messages: list[Message],
        model_id: str,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        if not self.client:
            raise ValueError(VISION_UNAVAILABLE_MSG)

        history = prepare_chat_history(messages, system_prompt=system_prompt)
        system_instruction = None
        body = history
        if body and body[0].get("role") == "system":
            system_instruction = body[0]["content"]
            body = body[1:]

        contents = [
            types.Content(
                role="user" if msg["role"] == "user" else "model",
                parts=[types.Part(text=msg["content"])],
            )
            for msg in body
        ]
        contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    types.Part(text=prompt),
                ],
            )
        )
        config = (
            types.GenerateContentConfig(system_instruction=system_instruction)
            if system_instruction
            else None
        )
        async for chunk in await self.client.aio.models.generate_content_stream(
            model=model_id,
            contents=contents,
            config=config,
        ):
            if chunk.text:
                yield chunk.text

