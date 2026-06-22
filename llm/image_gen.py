import base64
import logging
import aiohttp
from config import OPENROUTER_API_KEY, IMAGE_MODEL_ID

logger = logging.getLogger(__name__)


class ImageGenerationError(Exception):
    pass


async def generate_image(prompt: str) -> tuple[bytes, str]:
    """Generate an image and return (bytes, mime_type)."""
    if not OPENROUTER_API_KEY:
        raise ImageGenerationError("Image generation is not configured")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/gpt_groq_deepseek_bot",
    }
    payload = {
        "model": IMAGE_MODEL_ID,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
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
