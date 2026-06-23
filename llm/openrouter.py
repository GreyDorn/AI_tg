from typing import AsyncIterator
import aiohttp
import json
from config import OPENROUTER_API_KEY
from db.models import Message
from llm.base import BaseLLM
from llm.chat_context import prepare_chat_history


class OpenRouterLLM(BaseLLM):
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    async def stream(
        self,
        messages: list[Message],
        model_id: str,
        disable_thinking: bool = False,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        history = prepare_chat_history(messages, system_prompt=system_prompt)

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://t.me/gpt_groq_deepseek_bot",
        }
        payload = {
            "model": model_id,
            "messages": history,
            "stream": True,
            "max_tokens": 4096,
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

