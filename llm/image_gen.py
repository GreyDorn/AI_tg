import base64
import logging
import urllib.parse
import aiohttp
from config import (
    OPENROUTER_API_KEY,
    IMAGE_MODEL_ID,
    IMAGE_FALLBACK_MODEL_ID,
    IMAGE_MAX_TOKENS,
    IMAGE_FREE_MODEL,
    IMAGE_FREE_WIDTH,
    IMAGE_FREE_HEIGHT,
)

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"


class ImageGenerationError(Exception):
    pass


def _build_image_prompt(prompt: str) -> str:
    return f"Generate a high-quality image: {prompt}"


async def _generate_openrouter(model: str, prompt: str) -> tuple[bytes, str]:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/gpt_groq_deepseek_bot",
    }
    payload = {
        "model": model,
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


async def _generate_pollinations(
    prompt: str,
    *,
    model: str = IMAGE_FREE_MODEL,
    width: int = IMAGE_FREE_WIDTH,
    height: int = IMAGE_FREE_HEIGHT,
    enhance: bool = False,
) -> tuple[bytes, str]:
    params = urllib.parse.urlencode(
        {
            "model": model,
            "width": width,
            "height": height,
            "enhance": str(enhance).lower(),
            "nologo": "true",
        }
    )
    url = f"{POLLINATIONS_URL.format(prompt=urllib.parse.quote(prompt))}?{params}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            if resp.status != 200:
                raise ImageGenerationError(f"Free image API error {resp.status}")
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            data = await resp.read()
            if len(data) < 1000:
                raise ImageGenerationError("Free image API returned empty image")
            return data, content_type.split(";")[0]


async def generate_image(prompt: str) -> tuple[bytes, str]:
    """Generate a premium image via OpenRouter with Pollinations fallback."""
    errors: list[str] = []

    if OPENROUTER_API_KEY:
        for model in (IMAGE_MODEL_ID, IMAGE_FALLBACK_MODEL_ID):
            try:
                result = await _generate_openrouter(model, prompt)
                logger.info("Image generated via OpenRouter model=%s", model)
                return result
            except ImageGenerationError as exc:
                logger.warning("OpenRouter image failed model=%s: %s", model, exc)
                errors.append(str(exc))

    try:
        result = await _generate_pollinations(prompt, enhance=True)
        logger.info("Image generated via Pollinations fallback")
        return result
    except ImageGenerationError as exc:
        logger.warning("Pollinations image failed: %s", exc)
        errors.append(str(exc))

    raise ImageGenerationError("; ".join(errors[-2:]) if errors else "Image generation is not configured")


async def generate_image_free(prompt: str) -> tuple[bytes, str]:
    """Generate a free image via Pollinations (Flux)."""
    try:
        result = await _generate_pollinations(prompt, model=IMAGE_FREE_MODEL, enhance=True)
        logger.info("Free image generated via Pollinations model=%s", IMAGE_FREE_MODEL)
        return result
    except ImageGenerationError:
        # turbo is faster and also free on Pollinations
        result = await _generate_pollinations(prompt, model="turbo", enhance=False)
        logger.info("Free image generated via Pollinations model=turbo")
        return result
