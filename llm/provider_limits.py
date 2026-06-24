"""Probe external LLM providers for remaining quotas / balances (admin /stats)."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Mapping

import aiohttp

from config import (
    MODELS,
    GEMINI_API_KEY,
    GROQ_API_KEY,
    DEEPSEEK_API_KEY,
    POLLINATIONS_API_KEY,
    OPENROUTER_API_KEY,
)
from llm.provider_status import get_openrouter_status, OPENROUTER_CREDITS_URL

logger = logging.getLogger(__name__)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEEPSEEK_BALANCE_URL = "https://api.deepseek.com/user/balance"
POLLINATIONS_BALANCE_URL = "https://gen.pollinations.ai/account/balance"

PROBE_TIMEOUT = aiohttp.ClientTimeout(total=20)
CACHE_TTL_SEC = 60

_cache_text: str | None = None
_cache_at: float = 0.0


def _models_by_provider(provider: str) -> list[tuple[str, str]]:
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for model in MODELS.values():
        if model.provider != provider or model.id in seen:
            continue
        seen.add(model.id)
        result.append((model.id, model.name))
    return result


def _groq_limit_text(headers: Mapping[str, str]) -> str | None:
    rem_req = headers.get("x-ratelimit-remaining-requests")
    lim_req = headers.get("x-ratelimit-limit-requests")
    rem_tok = headers.get("x-ratelimit-remaining-tokens")
    lim_tok = headers.get("x-ratelimit-limit-tokens")
    if rem_req is None and rem_tok is None:
        return None
    parts = []
    if rem_req is not None and lim_req is not None:
        parts.append(f"{rem_req}/{lim_req} req/min")
    if rem_tok is not None and lim_tok is not None:
        parts.append(f"{rem_tok}/{lim_tok} tok/min")
    return ", ".join(parts) if parts else None


async def _probe_groq_model(session: aiohttp.ClientSession, model_id: str) -> str:
    if not GROQ_API_KEY:
        return "not configured"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    try:
        async with session.post(
            GROQ_CHAT_URL, json=payload, headers=headers, timeout=PROBE_TIMEOUT,
        ) as resp:
            limit_text = _groq_limit_text(resp.headers)
            if resp.status == 200:
                return limit_text or "available"
            if resp.status == 429:
                suffix = f" ({limit_text})" if limit_text else ""
                return f"limit reached{suffix}"
            body = await resp.text()
            return f"error {resp.status}: {body[:80]}"
    except Exception as exc:
        logger.warning("Groq probe failed model=%s: %s", model_id, exc)
        return f"probe failed: {exc}"


async def _probe_gemini_model(session: aiohttp.ClientSession, model_id: str) -> str:
    if not GEMINI_API_KEY:
        return "not configured"

    url = GEMINI_GENERATE_URL.format(model=model_id)
    params = {"key": GEMINI_API_KEY}
    payload = {
        "contents": [{"parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 1},
    }
    try:
        async with session.post(
            url, params=params, json=payload, timeout=PROBE_TIMEOUT,
        ) as resp:
            if resp.status == 200:
                return "available"
            if resp.status == 429:
                return "limit reached"
            body = await resp.text()
            low = body.lower()
            if "resource_exhausted" in low or "quota" in low:
                return "limit reached"
            if "unavailable" in low or resp.status == 503:
                return "busy — try later"
            return f"error {resp.status}: {body[:80]}"
    except Exception as exc:
        logger.warning("Gemini probe failed model=%s: %s", model_id, exc)
        return f"probe failed: {exc}"


async def _probe_deepseek_balance(session: aiohttp.ClientSession) -> str:
    if not DEEPSEEK_API_KEY:
        return "not configured"

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Accept": "application/json",
    }
    try:
        async with session.get(
            DEEPSEEK_BALANCE_URL, headers=headers, timeout=PROBE_TIMEOUT,
        ) as resp:
            if resp.status != 200:
                return f"error {resp.status}"
            data = await resp.json()
            if not data.get("is_available", True):
                return "balance empty"
            infos = data.get("balance_infos") or []
            usd = next((i for i in infos if i.get("currency") == "USD"), None)
            entry = usd or (infos[0] if infos else None)
            if not entry:
                return "no balance data"
            currency = entry.get("currency", "?")
            total = entry.get("total_balance", "?")
            granted = entry.get("granted_balance")
            topped = entry.get("topped_up_balance")
            text = f"{total} {currency}"
            if granted is not None or topped is not None:
                text += f" (granted {granted}, paid {topped})"
            return text
    except Exception as exc:
        logger.warning("DeepSeek balance probe failed: %s", exc)
        return f"probe failed: {exc}"


async def _probe_pollinations_balance(session: aiohttp.ClientSession) -> str:
    if not POLLINATIONS_API_KEY:
        return "not configured (free legacy images still work)"

    headers = {"Authorization": f"Bearer {POLLINATIONS_API_KEY}"}
    try:
        async with session.get(
            POLLINATIONS_BALANCE_URL, headers=headers, timeout=PROBE_TIMEOUT,
        ) as resp:
            if resp.status != 200:
                return f"error {resp.status}"
            data = await resp.json()
            balance = data.get("balance")
            if balance is None:
                return "no balance data"
            return f"{balance:.2f} pollen"
    except Exception as exc:
        logger.warning("Pollinations balance probe failed: %s", exc)
        return f"probe failed: {exc}"


async def _format_openrouter_line() -> str:
    if not OPENROUTER_API_KEY:
        return "not configured"
    status = await get_openrouter_status(force_probe=False)
    if not status.configured:
        return "not configured"
    parts = []
    if status.paid_available:
        parts.append("paid models on")
    else:
        parts.append("paid models off")
    if status.limit_remaining is not None:
        parts.append(f"${status.limit_remaining:.4f} left")
    if status.usage is not None:
        parts.append(f"${status.usage:.4f} used")
    if status.needs_topup:
        parts.append(f"top up: {OPENROUTER_CREDITS_URL}")
    if status.error:
        parts.append(status.error)
    return " · ".join(parts) if parts else "ok"


async def _build_limits_lines() -> list[str]:
    lines: list[str] = []

    gemini_models = _models_by_provider("google")
    groq_models = _models_by_provider("groq")

    async with aiohttp.ClientSession() as session:
        gemini_tasks = {
            name: _probe_gemini_model(session, model_id)
            for model_id, name in gemini_models
        }
        groq_tasks = {
            name: _probe_groq_model(session, model_id)
            for model_id, name in groq_models
        }
        deepseek_task = asyncio.create_task(_probe_deepseek_balance(session))
        pollinations_task = asyncio.create_task(_probe_pollinations_balance(session))
        openrouter_task = asyncio.create_task(_format_openrouter_line())

        gemini_results = await asyncio.gather(*gemini_tasks.values())
        groq_results = await asyncio.gather(*groq_tasks.values())
        deepseek_result = await deepseek_task
        pollinations_result = await pollinations_task
        openrouter_result = await openrouter_task

    if gemini_models:
        lines.append("<b>Gemini</b> (text + photos)")
        for (name, result) in zip(gemini_tasks.keys(), gemini_results):
            lines.append(f"• {name}: <b>{result}</b>")

    if groq_models:
        lines.append("<b>Groq</b> (per model, per minute)")
        for (name, result) in zip(groq_tasks.keys(), groq_results):
            lines.append(f"• {name}: <b>{result}</b>")

    lines.append("<b>DeepSeek</b>")
    lines.append(f"• Balance: <b>{deepseek_result}</b>")

    lines.append("<b>OpenRouter</b> (premium images)")
    lines.append(f"• <b>{openrouter_result}</b>")

    lines.append("<b>Pollinations</b> (gen images / music)")
    lines.append(f"• <b>{pollinations_result}</b>")

    return lines


async def get_provider_limits_text(*, use_cache: bool = True) -> str:
    global _cache_text, _cache_at

    now = time.monotonic()
    if use_cache and _cache_text and now - _cache_at < CACHE_TTL_SEC:
        return _cache_text

    try:
        body_lines = await _build_limits_lines()
        text = "<b>LLM provider limits</b>\n" + "\n".join(body_lines)
    except Exception as exc:
        logger.exception("Failed to build provider limits report")
        text = f"<b>LLM provider limits</b>\n⚠️ Could not load: {exc}"

    _cache_text = text
    _cache_at = now
    return text
