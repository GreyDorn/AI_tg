import base64
import logging
import urllib.parse
import aiohttp
from config import (
    OPENROUTER_API_KEY,
    IMAGE_MODELS,
    IMAGE_MAX_TOKENS,
    IMAGE_WIDTH,
    IMAGE_HEIGHT,
)

from llm.provider_status import set_openrouter_paid_available

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"


class ImageGenerationError(Exception):
    pass


def _build_image_prompt(prompt: str) -> str:
    return f"Generate a high-quality image: {prompt}"


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
        "modalities": ["image"],
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
        images = message.get("images") or []
        if not images:
            text_reply = (message.get("content") or "").strip()
            if text_reply:
                raise ImageGenerationError(f"Model returned text instead of image: {text_reply[:120]}")
            raise ImageGenerationError("Model returned no image")
        url = images[0]["image_url"]["url"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ImageGenerationError("Invalid image response from API") from exc

    if url.startswith("data:"):
        header, encoded = url.split(",", 1)
        mime_type = header.split(":")[1].split(";")[0]
        return base64.b64decode(encoded), mime_type

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                raise ImageGenerationError(f"Failed to download image: {resp.status}")
            content_type = resp.headers.get("Content-Type", "image/png")
            return await resp.read(), content_type.split(";")[0]


async def _generate_pollinations(model_id: str, prompt: str) -> tuple[bytes, str]:
    params = urllib.parse.urlencode(
        {
            "model": model_id,
            "width": IMAGE_WIDTH,
            "height": IMAGE_HEIGHT,
            "enhance": "true",
            "nologo": "true",
        }
    )
    url = f"{POLLINATIONS_URL.format(prompt=urllib.parse.quote(prompt))}?{params}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            if resp.status != 200:
                raise ImageGenerationError(f"API error {resp.status}")
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            data = await resp.read()
            if len(data) < 1000:
                raise ImageGenerationError("API returned empty image")
            return data, content_type.split(";")[0]


async def generate_image(prompt: str, model_key: str) -> tuple[bytes, str]:
    """Generate an image using the selected model."""
    if model_key not in IMAGE_MODELS:
        raise ImageGenerationError(f"Unknown image model: {model_key}")

    model = IMAGE_MODELS[model_key]

    if model.provider == "openrouter":
        result = await _generate_openrouter(model.id, prompt)
        logger.info("Image generated via OpenRouter model=%s", model.id)
        return result

    if model.provider == "pollinations":
        result = await _generate_pollinations(model.id, prompt)
        logger.info("Image generated via Pollinations model=%s", model.id)
        return result

    raise ImageGenerationError(f"Unsupported image provider: {model.provider}")
