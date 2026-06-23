import base64
import logging
import urllib.parse
import aiohttp
from config import (
    OPENROUTER_API_KEY,
    POLLINATIONS_API_KEY,
    IMAGE_MODELS,
    IMAGE_MAX_TOKENS,
    IMAGE_WIDTH,
    IMAGE_HEIGHT,
    DEFAULT_IMAGE_MODEL,
)

from llm.provider_status import set_openrouter_paid_available

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
POLLINATIONS_GEN_URL = "https://gen.pollinations.ai/image/{prompt}"
POLLINATIONS_LEGACY_URL = "https://image.pollinations.ai/prompt/{prompt}"
POLLINATIONS_FALLBACK_MODEL = "flux"

# Старый id turbo больше не принимается gen.pollinations.ai (возвращает JSON-ошибку).
_MODEL_ALIASES = {
    "turbo": "zimage",
}

_IMAGE_SIGNATURES = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"RIFF",  # WebP (RIFF....WEBP)
)


class ImageGenerationError(Exception):
    pass


def _resolve_pollinations_model(model_id: str) -> str:
    return _MODEL_ALIASES.get(model_id, model_id)


def _modalities_for_model(model_id: str) -> list[str]:
    model_lower = model_id.lower()
    if "gemini" in model_lower or model_id.startswith("google/"):
        return ["image", "text"]
    return ["image"]


def _is_image_bytes(data: bytes) -> bool:
    if len(data) < 12:
        return False
    if data.startswith(_IMAGE_SIGNATURES[:2]):
        return True
    return data.startswith(b"RIFF") and data[8:12] == b"WEBP"


def _validate_image_response(data: bytes, content_type: str) -> None:
    if len(data) < 1000:
        raise ImageGenerationError("API returned empty image")
    if not _is_image_bytes(data):
        snippet = data[:200].decode("utf-8", errors="replace")
        raise ImageGenerationError(f"API returned text instead of image: {snippet[:120]}")


def _build_image_prompt(prompt: str) -> str:
    return prompt.strip()


def _pollinations_headers() -> dict[str, str]:
    if POLLINATIONS_API_KEY:
        return {"Authorization": f"Bearer {POLLINATIONS_API_KEY}"}
    return {}


def _extract_images_from_message(message: dict) -> list[dict]:
    images = list(message.get("images") or [])
    content = message.get("content")

    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "image_url" and part.get("image_url"):
                images.append(part)
            elif part.get("type") == "image" and part.get("image"):
                url = part["image"].get("url") or part["image"].get("data")
                if url:
                    images.append({"image_url": {"url": url}})

    return images


async def _download_image_url(url: str) -> tuple[bytes, str]:
    if url.startswith("data:"):
        header, encoded = url.split(",", 1)
        mime_type = header.split(":")[1].split(";")[0]
        return base64.b64decode(encoded), mime_type

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                raise ImageGenerationError(f"Failed to download image: {resp.status}")
            content_type = resp.headers.get("Content-Type", "image/png")
            data = await resp.read()
            if not _is_image_bytes(data):
                raise ImageGenerationError("Downloaded file is not a valid image")
            return data, content_type.split(";")[0]


async def _generate_openrouter(model_id: str, prompt: str) -> tuple[bytes, str]:
    if not OPENROUTER_API_KEY:
        raise ImageGenerationError("OpenRouter API key is not configured")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/gpt_groq_deepseek_bot",
    }
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": _build_image_prompt(prompt)}],
        "modalities": _modalities_for_model(model_id),
        "max_tokens": IMAGE_MAX_TOKENS,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            OPENROUTER_URL,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                if resp.status == 402:
                    set_openrouter_paid_available(False)
                raise ImageGenerationError(f"API error {resp.status}: {error[:300]}")
            data = await resp.json()

    try:
        message = data["choices"][0]["message"]
        images = _extract_images_from_message(message)
        if not images:
            text_reply = (message.get("content") or "").strip()
            if isinstance(text_reply, list):
                text_reply = " ".join(
                    part.get("text", "") for part in text_reply if isinstance(part, dict)
                ).strip()
            if text_reply:
                raise ImageGenerationError(f"Model returned text instead of image: {text_reply[:120]}")
            raise ImageGenerationError("Model returned no image")
        url = images[0]["image_url"]["url"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ImageGenerationError("Invalid image response from API") from exc

    image_bytes, mime_type = await _download_image_url(url)
    if not _is_image_bytes(image_bytes):
        raise ImageGenerationError("Model returned invalid image data")
    return image_bytes, mime_type


async def _fetch_pollinations_image(url: str, headers: dict[str, str]) -> tuple[bytes, str]:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise ImageGenerationError(f"API error {resp.status}: {error[:300]}")
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            data = await resp.read()
    _validate_image_response(data, content_type)
    return data, content_type.split(";")[0]


async def _generate_pollinations_gen(model_id: str, prompt: str) -> tuple[bytes, str]:
    params = urllib.parse.urlencode(
        {
            "model": model_id,
            "width": IMAGE_WIDTH,
            "height": IMAGE_HEIGHT,
            "nologo": "true",
        }
    )
    url = f"{POLLINATIONS_GEN_URL.format(prompt=urllib.parse.quote(prompt))}?{params}"
    return await _fetch_pollinations_image(url, _pollinations_headers())


async def _generate_pollinations_legacy(model_id: str, prompt: str) -> tuple[bytes, str]:
    params = urllib.parse.urlencode(
        {
            "model": model_id,
            "width": IMAGE_WIDTH,
            "height": IMAGE_HEIGHT,
            "nologo": "true",
        }
    )
    url = f"{POLLINATIONS_LEGACY_URL.format(prompt=urllib.parse.quote(prompt))}?{params}"
    return await _fetch_pollinations_image(url, {})


async def _generate_pollinations(model_id: str, prompt: str) -> tuple[bytes, str]:
    model_id = _resolve_pollinations_model(model_id)
    errors: list[str] = []

    for attempt_name, generator in (
        ("legacy", _generate_pollinations_legacy),
        ("gen", _generate_pollinations_gen),
    ):
        try:
            result = await generator(model_id, prompt)
            logger.info("Image generated via Pollinations %s model=%s", attempt_name, model_id)
            return result
        except ImageGenerationError as exc:
            errors.append(f"{attempt_name}: {exc}")
            logger.warning("Pollinations %s failed model=%s: %s", attempt_name, model_id, exc)

    if model_id != POLLINATIONS_FALLBACK_MODEL:
        logger.warning(
            "Pollinations model=%s failed (%s), falling back to %s",
            model_id,
            "; ".join(errors),
            POLLINATIONS_FALLBACK_MODEL,
        )
        return await _generate_pollinations(POLLINATIONS_FALLBACK_MODEL, prompt)

    raise ImageGenerationError("; ".join(errors))


async def generate_image(prompt: str, model_key: str) -> tuple[bytes, str]:
    """Generate an image using the selected model."""
    if model_key not in IMAGE_MODELS:
        raise ImageGenerationError(f"Unknown image model: {model_key}")

    model = IMAGE_MODELS[model_key]

    if model.provider == "openrouter":
        try:
            result = await _generate_openrouter(model.id, prompt)
            logger.info("Image generated via OpenRouter model=%s", model.id)
            return result
        except ImageGenerationError as exc:
            logger.warning(
                "OpenRouter image failed model=%s, using Pollinations fallback: %s",
                model.id,
                exc,
            )
            fallback_model = IMAGE_MODELS[DEFAULT_IMAGE_MODEL].id
            result = await _generate_pollinations(fallback_model, prompt)
            logger.info("Image generated via Pollinations fallback model=%s", fallback_model)
            return result

    if model.provider == "pollinations":
        return await _generate_pollinations(model.id, prompt)

    raise ImageGenerationError(f"Unsupported image provider: {model.provider}")
