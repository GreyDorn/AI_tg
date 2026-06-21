import json
import aiohttp
from typing import AsyncIterator
from config import DEEPSEEK_API_KEY, MAX_CONTEXT_CHARS
from db.models import Message
from llm.base import BaseLLM

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"


class DeepSeekLLM(BaseLLM):
    async def stream(
        self, messages: list[Message], model_id: str, disable_thinking: bool = False
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
                        # deepseek-reasoner returns reasoning in separate field — skip it
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
