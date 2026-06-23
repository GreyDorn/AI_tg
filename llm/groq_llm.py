from typing import AsyncIterator
from groq import AsyncGroq
from config import GROQ_API_KEY, CHAT_SYSTEM_PROMPT
from db.models import Message
from llm.base import BaseLLM
from llm.chat_context import prepare_chat_history

_QWEN_THINK_OPEN = chr(60) + "think" + chr(62)
_QWEN_THINK_CLOSE = chr(60) + "/" + "think" + chr(62)

THINKING_TAGS = (
    ("<think>", "</think>"),
    (_QWEN_THINK_OPEN, _QWEN_THINK_CLOSE),
)

COMPOUND_MODEL_IDS = frozenset({"groq/compound", "groq/compound-mini"})
GPT_OSS_MODEL_IDS = frozenset({"openai/gpt-oss-20b", "openai/gpt-oss-120b"})
COMPOUND_SYSTEM_PROMPT = (
    CHAT_SYSTEM_PROMPT + "\n\n"
    "Reply with only the final answer. "
    "No reasoning, no explanation, no headers."
)


class GroqLLM(BaseLLM):
    def __init__(self):
        self.client = AsyncGroq(api_key=GROQ_API_KEY)

    async def stream(
        self,
        messages: list[Message],
        model_id: str,
        disable_thinking: bool = False,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        if model_id in COMPOUND_MODEL_IDS and disable_thinking:
            prompt = COMPOUND_SYSTEM_PROMPT
        elif system_prompt:
            prompt = system_prompt
        else:
            prompt = None
        history = prepare_chat_history(messages, system_prompt=prompt)

        request_kwargs: dict = {
            "model": model_id,
            "messages": history,
            "stream": True,
            "max_tokens": 4096,
        }
        if model_id in GPT_OSS_MODEL_IDS and disable_thinking:
            request_kwargs["include_reasoning"] = False

        stream = await self.client.chat.completions.create(**request_kwargs)

        in_think = False
        active_close_tag = ""
        finish_reason = None
        async for chunk in stream:
            choice = chunk.choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = choice.delta.content
            if not delta:
                continue
            if disable_thinking:
                clean, in_think, active_close_tag = self._filter_thinking(
                    delta, in_think, active_close_tag
                )
                if clean:
                    yield clean
            else:
                yield delta

        if finish_reason == "length":
            yield "\n\n⚠️ _Response truncated — token limit reached. Ask me to continue._"

    @staticmethod
    def _find_open_tag(text: str, start: int) -> tuple[int, str, str] | None:
        best: tuple[int, str, str] | None = None
        for open_tag, close_tag in THINKING_TAGS:
            if not open_tag:
                continue
            pos = text.find(open_tag, start)
            if pos != -1 and (best is None or pos < best[0]):
                best = (pos, open_tag, close_tag)
        return best

    @classmethod
    def _filter_thinking(
        cls, text: str, in_think: bool, active_close_tag: str
    ) -> tuple[str, bool, str]:
        """Strip reasoning blocks from streamed Groq output."""
        result = ""
        i = 0
        while i < len(text):
            if not in_think:
                match = cls._find_open_tag(text, i)
                if match is None:
                    result += text[i:]
                    break
                pos, open_tag, close_tag = match
                result += text[i:pos]
                in_think = True
                active_close_tag = close_tag
                i = pos + len(open_tag)
            else:
                end = text.find(active_close_tag, i)
                if end == -1:
                    break
                close_len = len(active_close_tag)
                in_think = False
                active_close_tag = ""
                i = end + close_len
        return result, in_think, active_close_tag

