"""Async client for MAX Bot API."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from config import MAX_API_URL, MAX_BOT_TOKEN

logger = logging.getLogger(__name__)


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": MAX_BOT_TOKEN,
        "Content-Type": "application/json",
    }


async def get_me() -> dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{MAX_API_URL}/me",
            headers=_auth_headers(),
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()


async def register_webhook(url: str, secret: str = "") -> dict[str, Any]:
    body: dict[str, Any] = {
        "url": url,
        "update_types": ["message_created", "bot_started"],
    }
    if secret:
        body["secret"] = secret

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{MAX_API_URL}/subscriptions",
            headers=_auth_headers(),
            json=body,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            text = await resp.text()
            if not resp.ok:
                logger.error("register_webhook %s: %s", resp.status, text[:500])
                resp.raise_for_status()
            return await resp.json()


async def send_message(
    *,
    user_id: int | None = None,
    chat_id: int | None = None,
    text: str,
) -> bool:
    params: dict[str, int] = {}
    if user_id is not None:
        params["user_id"] = user_id
    elif chat_id is not None:
        params["chat_id"] = chat_id
    else:
        logger.warning("send_message: no recipient")
        return False

    body = {"text": text[:4000]}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{MAX_API_URL}/messages",
            headers=_auth_headers(),
            params=params,
            json=body,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.ok:
                return True
            text_resp = await resp.text()
            logger.error("POST /messages %s: %s", resp.status, text_resp[:500])
            return False
