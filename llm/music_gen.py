import logging
import urllib.parse
import aiohttp
from config import POLLINATIONS_API_KEY, MUSIC_MODELS

logger = logging.getLogger(__name__)

POLLINATIONS_AUDIO_URL = "https://gen.pollinations.ai/audio/{prompt}"

_AUDIO_SIGNATURES = (
    b"ID3",  # MP3 with ID3 tag
    b"\xff\xfb",  # MP3 frame sync
    b"\xff\xf3",
    b"\xff\xf2",
    b"RIFF",  # WAV
    b"fLaC",  # FLAC
    b"OggS",  # OGG
)


class MusicGenerationError(Exception):
    pass


def is_pollinations_music_configured() -> bool:
    return bool(POLLINATIONS_API_KEY)


def _is_audio_bytes(data: bytes) -> bool:
    if len(data) < 12:
        return False
    if data.startswith(_AUDIO_SIGNATURES[:3]):
        return True
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return True
    return data.startswith(_AUDIO_SIGNATURES[4:])


def _extension_for_mime(mime_type: str) -> str:
    return {
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/flac": "flac",
        "audio/ogg": "ogg",
        "audio/opus": "opus",
    }.get(mime_type.split(";")[0].strip().lower(), "mp3")


async def _generate_pollinations_audio(
    model_id: str,
    prompt: str,
    duration: int,
) -> tuple[bytes, str]:
    if not POLLINATIONS_API_KEY:
        raise MusicGenerationError(
            "Pollinations API key is not configured. Add POLLINATIONS_API_KEY to .env"
        )

    params = urllib.parse.urlencode(
        {
            "model": model_id,
            "duration": duration,
        }
    )
    url = f"{POLLINATIONS_AUDIO_URL.format(prompt=urllib.parse.quote(prompt))}?{params}"
    headers = {"Authorization": f"Bearer {POLLINATIONS_API_KEY}"}

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=180),
        ) as resp:
            if resp.status == 401:
                raise MusicGenerationError("Invalid Pollinations API key (401)")
            if resp.status == 402:
                raise MusicGenerationError("Insufficient Pollinations credits (402)")
            if resp.status != 200:
                error = await resp.text()
                raise MusicGenerationError(f"API error {resp.status}: {error[:300]}")
            content_type = resp.headers.get("Content-Type", "audio/mpeg")
            data = await resp.read()

    if len(data) < 1000:
        snippet = data[:200].decode("utf-8", errors="replace")
        raise MusicGenerationError(f"API returned empty audio: {snippet[:120]}")
    if not _is_audio_bytes(data):
        snippet = data[:200].decode("utf-8", errors="replace")
        raise MusicGenerationError(f"API returned text instead of audio: {snippet[:120]}")
    return data, content_type.split(";")[0]


async def generate_music(prompt: str, model_key: str) -> tuple[bytes, str, str]:
    """Generate music. Returns (audio_bytes, mime_type, file_extension)."""
    if model_key not in MUSIC_MODELS:
        raise MusicGenerationError(f"Unknown music model: {model_key}")

    model = MUSIC_MODELS[model_key]

    if model.provider == "pollinations":
        audio_bytes, mime_type = await _generate_pollinations_audio(
            model.id,
            prompt,
            model.duration_seconds,
        )
        ext = _extension_for_mime(mime_type)
        logger.info("Music generated via Pollinations model=%s ext=%s", model.id, ext)
        return audio_bytes, mime_type, ext

    raise MusicGenerationError(f"Unsupported music provider: {model.provider}")
