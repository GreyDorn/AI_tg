import json
import logging
import aiohttp
from typing import AsyncIterator
from config import DEEPSEEK_API_KEY, OPENROUTER_API_KEY, MAX_CONTEXT_CHARS
from db.models import Message
from llm.base import BaseLLM
from llm.groq_llm import GroqLLM
from llm.openrouter import OpenRouterLLM

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

# Порядок: прямой DeepSeek API → OpenRouter → Groq (бесплатный запасной вариант)
ROUTES: dict[str, list[tuple[str, str]]] = {
    "deepseek-chat": [
        ("direct", "deepseek-chat"),
        ("openrouter", "deepseek/deepseek-chat"),
        ("groq", "llama-3.3-70b-versatile"),
    ],
    "deepseek-reasoner": [
        ("direct", "deepseek-reasoner"),
        ("openrouter", "deepseek/deepseek-r1"),
        ("groq", "openai/gpt-oss-120b"),
    ],
}


def _is_retryable_error(exc: Exception) -> bool:
    error_str = str(exc).lower()
    return (
        "402" in str(exc)
        or "insufficient balance" in error_str
        or "insufficient credits" in error_str
        or "payment required" in error_str
        or "404" in str(exc)
        or "no endpoints found" in error_str
        or "decommissioned" in error_str
    )


class DeepSeekLLM(BaseLLM):
    def __init__(self) -> None:
        self._groq = GroqLLM()
        self._openrouter = OpenRouterLLM()

    async def stream(
        self, messages: list[Message], model_id: str, disable_thinking: bool = False
    ) -> AsyncIterator[str]:
        routes = ROUTES.get(model_id, [("direct", model_id)])
        errors: list[str] = []

        for backend, actual_model in routes:
            if backend == "direct" and not DEEPSEEK_API_KEY:
                continue
            if backend == "openrouter" and not OPENROUTER_API_KEY:
                continue

            try:
                stream: AsyncIterator[str]
                if backend == "direct":
                    stream = self._stream_direct(messages, actual_model)
                elif backend == "openrouter":
                    stream = self._openrouter.stream(messages, actual_model, disable_thinking)
                elif backend == "groq":
                    stream = self._groq.stream(messages, actual_model, disable_thinking)
                else:
                    continue

                async for chunk in stream:
                    yield chunk

                logger.info("DeepSeek routed via %s model=%s", backend, actual_model)
                return
            except Exception as exc:
                logger.warning("DeepSeek backend %s (%s) failed: %s", backend, actual_model, exc)
                errors.append(f"{backend}: {exc}")
                if not _is_retryable_error(exc):
                    raise
                continue

        raise Exception("; ".join(errors[-3:]) if errors else f"DeepSeek model {model_id} unavailable")

    async def _stream_direct(
        self, messages: list[Message], model_id: str
    ) -> AsyncIterator[str]:
        history = self._build_history(messages)
        history = self._trim_context(history)

        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_id,
            "messages": history,
            "stream": True,
            "max_tokens": 4096,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise Exception(f"Error code: {resp.status} - {error}")

                async for line in resp.content:
                    line = line.decode(errors="replace").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"]
                        content = delta.get("content") or ""
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    def _trim_context(self, history: list[dict]) -> list[dict]:
        total = sum(len(m["content"]) for m in history)
        while total > MAX_CONTEXT_CHARS and len(history) > 1:
            removed = history.pop(0)
            total -= len(removed["content"])
        return history
