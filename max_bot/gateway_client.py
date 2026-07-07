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


async def generate_image(
    model_key: str,
    prompt: str,
) -> tuple[bytes, str, str, str]:
    """Returns image_bytes, mime_type, model_key, model_name."""
    if not LLM_GATEWAY_URL or not GATEWAY_INTERNAL_KEY:
        raise GatewayError("LLM gateway not configured", LlmErrorKind.GENERIC)

    import base64

    url = f"{LLM_GATEWAY_URL.rstrip('/')}/v1/image"
    headers = {"X-Internal-Key": GATEWAY_INTERNAL_KEY, "Content-Type": "application/json"}
    payload = {"model_key": model_key, "prompt": prompt}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=180),
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status == 403:
                raise GatewayError("gateway auth failed", LlmErrorKind.GENERIC)
            if resp.status != 200:
                raise GatewayError(str(data.get("error") or "gateway error"), LlmErrorKind.GENERIC)
            raw = data.get("image_base64")
            if not raw:
                raise GatewayError("empty image", LlmErrorKind.GENERIC)
            image_bytes = base64.b64decode(raw)
            mime_type = str(data.get("mime_type") or "image/png")
            return (
                image_bytes,
                mime_type,
                str(data.get("model_key") or model_key),
                str(data.get("model_name") or model_key),
            )
