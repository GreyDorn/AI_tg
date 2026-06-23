import logging
import aiohttp
from config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

OPENROUTER_PROBE_URL = "https://openrouter.ai/api/v1/chat/completions"

_openrouter_paid_available: bool | None = None


def is_openrouter_paid_available() -> bool:
    if _openrouter_paid_available is not None:
        return _openrouter_paid_available
    return bool(OPENROUTER_API_KEY)


def set_openrouter_paid_available(available: bool) -> None:
    global _openrouter_paid_available
    _openrouter_paid_available = available
    logger.info("OpenRouter paid models available: %s", available)


async def probe_openrouter_paid() -> bool:
    """Check whether OpenRouter paid endpoints accept requests (not 402)."""
    global _openrouter_paid_available

    if not OPENROUTER_API_KEY:
        _openrouter_paid_available = False
        return False

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "deepseek/deepseek-chat",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPENROUTER_PROBE_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    _openrouter_paid_available = True
                elif resp.status == 402:
                    _openrouter_paid_available = False
                else:
                    # Other errors: keep models visible, runtime errors will explain.
                    _openrouter_paid_available = True
    except Exception as exc:
        logger.warning("OpenRouter probe failed: %s", exc)
        _openrouter_paid_available = bool(OPENROUTER_API_KEY)

    logger.info("OpenRouter paid models available: %s", _openrouter_paid_available)
    return _openrouter_paid_available


def get_available_image_models() -> dict:
    from config import IMAGE_MODELS, DEFAULT_IMAGE_MODEL

    if is_openrouter_paid_available():
        return dict(IMAGE_MODELS)

    available = {
        key: model
        for key, model in IMAGE_MODELS.items()
        if model.provider != "openrouter"
    }
    return available or {DEFAULT_IMAGE_MODEL: IMAGE_MODELS[DEFAULT_IMAGE_MODEL]}


def resolve_image_model_key(current: str) -> str:
    from config import DEFAULT_IMAGE_MODEL

    available = get_available_image_models()
    if current in available:
        return current
    if DEFAULT_IMAGE_MODEL in available:
        return DEFAULT_IMAGE_MODEL
    return next(iter(available))
