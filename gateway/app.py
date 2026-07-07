"""Internal LLM gateway for MAX bot on RU VPS."""

from __future__ import annotations

import asyncio
import base64
import logging
import sys
from dataclasses import dataclass

from aiohttp import web

from config import (
    GATEWAY_HOST,
    GATEWAY_INTERNAL_KEY,
    GATEWAY_PORT,
    MODELS,
    CHAT_SYSTEM_PROMPT,
    DEFAULT_VISION_PROMPT,
    resolve_model_key,
)
from core.errors import classify_llm_error
from core.types import LlmErrorKind
from llm import get_llm
from llm.gemini import GeminiLLM
from llm.image_gen import generate_image, ImageGenerationError
from llm.provider_status import resolve_image_model_key

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)
_vision_llm = GeminiLLM()


@dataclass
class _ChatMessage:
    role: str
    content: str


def _check_auth(request: web.Request) -> web.Response | None:
    if not GATEWAY_INTERNAL_KEY:
        return web.json_response({"error": "gateway not configured"}, status=503)
    got = request.headers.get("X-Internal-Key", "")
    if got != GATEWAY_INTERNAL_KEY:
        return web.json_response({"error": "forbidden"}, status=403)
    return None


async def _collect_stream(stream) -> str:
    parts: list[str] = []
    async for chunk in stream:
        if chunk:
            parts.append(chunk)
    return "".join(parts)


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def chat(request: web.Request) -> web.Response:
    auth_error = _check_auth(request)
    if auth_error:
        return auth_error

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    model_key = resolve_model_key(str(data.get("model_key") or ""))
    raw_messages = data.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        return web.json_response({"error": "messages required"}, status=400)

    messages: list[_ChatMessage] = []
    for item in raw_messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "")
        if role in ("user", "assistant") and content:
            messages.append(_ChatMessage(role=role, content=content))

    if not messages:
        return web.json_response({"error": "no valid messages"}, status=400)

    model_cfg = MODELS[model_key]
    llm, model_id, disable_thinking = get_llm(model_key)

    try:
        stream = llm.stream(
            messages,  # type: ignore[arg-type]
            model_id,
            disable_thinking,
            system_prompt=CHAT_SYSTEM_PROMPT,
        )
        text = await _collect_stream(stream)
    except Exception as exc:
        kind = classify_llm_error(exc)
        logger.exception("LLM error model=%s kind=%s", model_key, kind.value)
        return web.json_response(
            {"error": str(exc), "kind": kind.value},
            status=502,
        )

    if not text.strip():
        return web.json_response(
            {"error": "empty response", "kind": LlmErrorKind.EMPTY_RESPONSE.value},
            status=502,
        )

    return web.json_response(
        {
            "text": text,
            "model_key": model_key,
            "model_name": model_cfg.name,
        }
    )


async def vision(request: web.Request) -> web.Response:
    auth_error = _check_auth(request)
    if auth_error:
        return auth_error

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    model_key = resolve_model_key(str(data.get("model_key") or ""))
    vision_cfg = MODELS.get(model_key)
    if not vision_cfg or not vision_cfg.supports_vision or vision_cfg.provider != "google":
        model_key = "gemini-2.5-flash-lite"
        vision_cfg = MODELS[model_key]

    raw_b64 = data.get("image_base64")
    if not raw_b64:
        return web.json_response({"error": "image_base64 required"}, status=400)

    try:
        image_bytes = base64.b64decode(raw_b64)
    except Exception:
        return web.json_response({"error": "invalid image_base64"}, status=400)

    if not image_bytes:
        return web.json_response({"error": "empty image"}, status=400)
    if len(image_bytes) > 8 * 1024 * 1024:
        return web.json_response({"error": "image too large"}, status=400)

    mime_type = str(data.get("mime_type") or "image/jpeg")
    prompt = str(data.get("prompt") or DEFAULT_VISION_PROMPT).strip() or DEFAULT_VISION_PROMPT

    raw_messages = data.get("messages") or []
    messages: list[_ChatMessage] = []
    if isinstance(raw_messages, list):
        for item in raw_messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "")
            if role in ("user", "assistant") and content:
                messages.append(_ChatMessage(role=role, content=content))

    try:
        stream = _vision_llm.stream_vision(
            image_bytes,
            mime_type,
            prompt,
            messages,  # type: ignore[arg-type]
            vision_cfg.id,
        )
        text = await _collect_stream(stream)
    except Exception as exc:
        kind = classify_llm_error(exc, vision_mode=True)
        logger.exception("Vision error model=%s kind=%s", model_key, kind.value)
        return web.json_response(
            {"error": str(exc), "kind": kind.value},
            status=502,
        )

    if not text.strip():
        return web.json_response(
            {"error": "empty response", "kind": LlmErrorKind.EMPTY_RESPONSE.value},
            status=502,
        )

    return web.json_response(
        {
            "text": text,
            "model_key": model_key,
            "model_name": vision_cfg.name,
        }
    )


async def image(request: web.Request) -> web.Response:
    auth_error = _check_auth(request)
    if auth_error:
        return auth_error

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        return web.json_response({"error": "prompt required"}, status=400)
    if len(prompt) > 1000:
        return web.json_response({"error": "prompt too long"}, status=400)

    model_key = resolve_image_model_key(str(data.get("model_key") or ""))

    try:
        image_bytes, mime_type = await generate_image(prompt, model_key)
    except ImageGenerationError as exc:
        logger.exception("Image error model=%s", model_key)
        return web.json_response({"error": str(exc), "kind": "generic"}, status=502)
    except Exception as exc:
        logger.exception("Image error model=%s", model_key)
        return web.json_response({"error": str(exc), "kind": "generic"}, status=502)

    from config import IMAGE_MODELS
    model_cfg = IMAGE_MODELS[model_key]
    return web.json_response(
        {
            "image_base64": base64.b64encode(image_bytes).decode("ascii"),
            "mime_type": mime_type,
            "model_key": model_key,
            "model_name": model_cfg.name,
        }
    )


def create_app() -> web.Application:
    app = web.Application(client_max_size=16 * 1024 * 1024)
    app.router.add_get("/health", health)
    app.router.add_post("/v1/chat", chat)
    app.router.add_post("/v1/vision", vision)
    app.router.add_post("/v1/image", image)
    return app


async def main() -> None:
    if not GATEWAY_INTERNAL_KEY:
        raise ValueError("GATEWAY_INTERNAL_KEY не задан в .env")

    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, GATEWAY_HOST, GATEWAY_PORT)
    await site.start()
    logger.info("LLM gateway listening on %s:%s", GATEWAY_HOST, GATEWAY_PORT)

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
