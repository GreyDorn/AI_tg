import asyncio
import logging
from dataclasses import dataclass
import aiohttp
from config import OPENROUTER_API_KEY, OPENROUTER_PROBE_INTERVAL

logger = logging.getLogger(__name__)

OPENROUTER_PROBE_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
OPENROUTER_CREDITS_URL = "https://openrouter.ai/credits"

_openrouter_paid_available: bool | None = None
_probe_task: asyncio.Task | None = None


@dataclass
class OpenRouterStatus:
    configured: bool
    paid_available: bool
    limit_remaining: float | None = None
    usage: float | None = None
    is_free_tier: bool | None = None
    error: str | None = None

    @property
    def needs_topup(self) -> bool:
        if not self.configured:
            return True
        if not self.paid_available:
            return True
        if self.limit_remaining is not None and self.limit_remaining <= 0:
            return True
        return False


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


async def _fetch_openrouter_key_info() -> dict | None:
    if not OPENROUTER_API_KEY:
        return None

    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                OPENROUTER_KEY_URL,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    return None
                payload = await resp.json()
                data = payload.get("data")
                return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("OpenRouter key info failed: %s", exc)
        return None


async def get_openrouter_status(force_probe: bool = False) -> OpenRouterStatus:
    if not OPENROUTER_API_KEY:
        return OpenRouterStatus(configured=False, paid_available=False)

    if force_probe or _openrouter_paid_available is None:
        await probe_openrouter_paid()

    key_info = await _fetch_openrouter_key_info()
    if not key_info:
        return OpenRouterStatus(
            configured=True,
            paid_available=is_openrouter_paid_available(),
            error="Could not load key info",
        )

    limit_remaining = key_info.get("limit_remaining")
    usage = key_info.get("usage")
    return OpenRouterStatus(
        configured=True,
        paid_available=is_openrouter_paid_available(),
        limit_remaining=float(limit_remaining) if limit_remaining is not None else None,
        usage=float(usage) if usage is not None else None,
        is_free_tier=bool(key_info.get("is_free_tier")),
    )


async def openrouter_probe_loop() -> None:
    """Re-check OpenRouter credits periodically (after manual top-up)."""
    while True:
        await asyncio.sleep(OPENROUTER_PROBE_INTERVAL)
        try:
            await probe_openrouter_paid()
        except Exception as exc:
            logger.warning("OpenRouter periodic probe failed: %s", exc)


def start_openrouter_probe_loop() -> asyncio.Task:
    global _probe_task
    if _probe_task is None or _probe_task.done():
        _probe_task = asyncio.create_task(openrouter_probe_loop())
    return _probe_task


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
