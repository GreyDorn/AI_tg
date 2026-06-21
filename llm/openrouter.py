from typing import AsyncIterator
import aiohttp
import json
from config import OPENROUTER_API_KEY, MAX_CONTEXT_CHARS
from db.models import Message
from llm.base import BaseLLM


class OpenRouterLLM(BaseLLM):
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    async def stream(
        self, messages: list[Message], model_id: str, disable_thinking: bool = False
    ) -> AsyncIterator[str]:
        history = self._build_history(messages)
        history = self._trim_context(history)

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://t.me/gpt_groq_deepseek_bot",
        }
        payload = {
            "model": model_id,
            "messages": history,
            "stream": True,
            "max_tokens": 2048,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.BASE_URL, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise Exception(f"{resp.status} {error}")

                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    def _trim_context(self, history: list[dict]) -> list[dict]:
        total = sum(len(m["content"]) for m in history)
        while total > MAX_CONTEXT_CHARS and len(history) > 1:
            removed = history.pop(0)
            total -= len(removed["content"])
        return history
