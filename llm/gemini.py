import asyncio
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
VISION_FALLBACK_MODELS = ("gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-2.5-flash")
VISION_SYSTEM_PROMPT = (
    "You analyze images in a Telegram chat. Describe what you see clearly and answer "
    "the user's question. Reply in the same language the user uses."
)
VISION_MAX_RETRIES = 3
VISION_RETRY_DELAY_SEC = 2.0


def _is_retryable_error(exc: Exception) -> bool:
    error_str = str(exc).lower()
    return (
        "503" in str(exc)
        or "429" in str(exc)
        or "quota" in error_str
        or "resource_exhausted" in error_str
        or "unavailable" in error_str
        or "overloaded" in error_str
        or "high demand" in error_str
    )


def _gemini_role(role: str) -> str:
    return "user" if role == "user" else "model"


def _append_text_content(contents: list[types.Content], role: str, text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    if contents and contents[-1].role == role:
        contents[-1].parts.append(types.Part(text=text))
        return
    contents.append(types.Content(role=role, parts=[types.Part(text=text)]))


def _build_text_contents(body: list[dict]) -> list[types.Content]:
    contents: list[types.Content] = []
    for msg in body:
        _append_text_content(contents, _gemini_role(msg["role"]), msg.get("content", ""))
    return contents


def _build_vision_contents(
    body: list[dict],
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
) -> list[types.Content]:
    contents = _build_text_contents(body)
    image_parts = [
        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        types.Part(text=prompt),
    ]
    if contents and contents[-1].role == "user":
        contents[-1].parts.extend(image_parts)
    else:
        contents.append(types.Content(role="user", parts=image_parts))
    return contents


def _vision_model_candidates(model_id: str) -> list[str]:
    models: list[str] = []
    for candidate in (model_id, *VISION_FALLBACK_MODELS):
        if candidate not in models:
            models.append(candidate)
    return models


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

        contents = _build_text_contents(body)
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

    async def _stream_vision_once(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
        messages: list[Message],
        model_id: str,
        system_prompt: str,
    ) -> AsyncIterator[str]:
        history = prepare_chat_history(messages, system_prompt=system_prompt)
        system_instruction = None
        body = history
        if body and body[0].get("role") == "system":
            system_instruction = body[0]["content"]
            body = body[1:]

        contents = _build_vision_contents(body, image_bytes, mime_type, prompt)
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

        vision_system_prompt = (
            system_prompt if system_prompt is not None else VISION_SYSTEM_PROMPT
        )
        last_exc: Exception | None = None
        for candidate_model in _vision_model_candidates(model_id):
            for attempt in range(VISION_MAX_RETRIES):
                try:
                    async for chunk in self._stream_vision_once(
                        image_bytes,
                        mime_type,
                        prompt,
                        messages,
                        candidate_model,
                        vision_system_prompt,
                    ):
                        yield chunk
                    return
                except Exception as exc:
                    last_exc = exc
                    if not _is_retryable_error(exc):
                        raise
                    logger.warning(
                        "Gemini vision failed model=%s attempt=%s/%s: %s",
                        candidate_model,
                        attempt + 1,
                        VISION_MAX_RETRIES,
                        exc,
                    )
                    if attempt + 1 < VISION_MAX_RETRIES:
                        await asyncio.sleep(VISION_RETRY_DELAY_SEC * (attempt + 1))
            logger.warning("Gemini vision switching model after failures: %s", candidate_model)

        if last_exc:
            raise last_exc
