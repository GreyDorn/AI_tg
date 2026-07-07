"""Call LLM gateway on DE VPS."""

from __future__ import annotations

import logging

import aiohttp

from config import GATEWAY_INTERNAL_KEY, LLM_GATEWAY_URL
from core.types import LlmErrorKind

logger = logging.getLogger(__name__)


class GatewayError(Exception):
    def __init__(self, message: str, kind: LlmErrorKind = LlmErrorKind.GENERIC):
        super().__init__(message)
        self.kind = kind


async def complete_chat(model_key: str, messages: list[dict[str, str]]) -> str:
    if not LLM_GATEWAY_URL or not GATEWAY_INTERNAL_KEY:
        raise GatewayError("LLM gateway not configured", LlmErrorKind.GENERIC)

    url = f"{LLM_GATEWAY_URL.rstrip('/')}/v1/chat"
    headers = {"X-Internal-Key": GATEWAY_INTERNAL_KEY, "Content-Type": "application/json"}
    payload = {"model_key": model_key, "messages": messages}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status == 403:
                raise GatewayError("gateway auth failed", LlmErrorKind.GENERIC)
            if resp.status != 200:
                kind_str = str(data.get("kind") or "generic")
                try:
                    kind = LlmErrorKind(kind_str)
                except ValueError:
                    kind = LlmErrorKind.GENERIC
                raise GatewayError(str(data.get("error") or "gateway error"), kind)
            text = str(data.get("text") or "")
            if not text.strip():
                raise GatewayError("empty response", LlmErrorKind.EMPTY_RESPONSE)
            return text


async def complete_vision(
    model_key: str,
    messages: list[dict[str, str]],
    *,
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
) -> str:
    if not LLM_GATEWAY_URL or not GATEWAY_INTERNAL_KEY:
        raise GatewayError("LLM gateway not configured", LlmErrorKind.GENERIC)

    import base64

    url = f"{LLM_GATEWAY_URL.rstrip('/')}/v1/vision"
    headers = {"X-Internal-Key": GATEWAY_INTERNAL_KEY, "Content-Type": "application/json"}
    payload = {
        "model_key": model_key,
        "messages": messages,
        "image_base64": base64.b64encode(image_bytes).decode("ascii"),
        "mime_type": mime_type,
        "prompt": prompt,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status == 403:
                raise GatewayError("gateway auth failed", LlmErrorKind.GENERIC)
            if resp.status != 200:
                kind_str = str(data.get("kind") or "generic")
                try:
                    kind = LlmErrorKind(kind_str)
                except ValueError:
                    kind = LlmErrorKind.GENERIC
                raise GatewayError(str(data.get("error") or "gateway error"), kind)
            text = str(data.get("text") or "")
            if not text.strip():
                raise GatewayError("empty response", LlmErrorKind.EMPTY_RESPONSE)
            return text
