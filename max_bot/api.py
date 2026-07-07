"""Async client for MAX Bot API."""

from __future__ import annotations

import asyncio
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
        "update_types": ["message_created", "message_callback", "bot_started"],
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


async def answer_callback(callback_id: str, notification: str = "") -> None:
    params = {"callback_id": callback_id}
    body: dict[str, str] = {}
    if notification:
        body["notification"] = notification[:200]
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{MAX_API_URL}/answers",
            headers=_auth_headers(),
            params=params,
            json=body,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if not resp.ok:
                text = await resp.text()
                logger.error("POST /answers %s: %s", resp.status, text[:500])


def _image_payload_from_upload(result: dict) -> dict:
    """MAX image upload returns {photos: {...}} instead of flat token."""
    if not isinstance(result, dict):
        raise RuntimeError(f"Invalid upload response: {result!r}")
    if "photos" in result:
        return {"photos": result["photos"]}
    token = result.get("token")
    if token:
        return {"token": str(token)}
    raise RuntimeError(f"No image token in upload response: {result!r}")


async def send_message(
    *,
    user_id: int | None = None,
    chat_id: int | None = None,
    text: str,
    attachments: list[dict] | None = None,
) -> bool:
    params: dict[str, int] = {}
    if user_id is not None:
        params["user_id"] = user_id
    elif chat_id is not None:
        params["chat_id"] = chat_id
    else:
        logger.warning("send_message: no recipient")
        return False

    body: dict[str, Any] = {"text": text[:4000]}
    if attachments:
        body["attachments"] = attachments
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


async def upload_image_bytes(image_bytes: bytes, *, filename: str, mime_type: str) -> dict:
    """Upload image to MAX, return attachment payload for POST /messages."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{MAX_API_URL}/uploads",
            headers={"Authorization": MAX_BOT_TOKEN},
            params={"type": "image"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        upload_url = data.get("url")
        if not upload_url:
            raise RuntimeError(f"No upload URL: {data}")

        form = aiohttp.FormData()
        form.add_field("data", image_bytes, filename=filename, content_type=mime_type)
        async with session.post(upload_url, data=form, timeout=aiohttp.ClientTimeout(total=120)) as up:
            up.raise_for_status()
            result = await up.json(content_type=None)
        if not isinstance(result, dict):
            raise RuntimeError(f"Invalid upload response: {result!r}")
        payload = _image_payload_from_upload(result)

    await asyncio.sleep(2)
    return payload


async def send_image_message(
    *,
    user_id: int,
    text: str,
    image_payload: dict,
    extra_attachments: list[dict] | None = None,
) -> bool:
    attachments: list[dict] = [{"type": "image", "payload": image_payload}]
    if extra_attachments:
        attachments.extend(extra_attachments)

    for attempt in range(3):
        ok = await send_message(user_id=user_id, text=text, attachments=attachments)
        if ok:
            return True
        if attempt < 2:
            await asyncio.sleep(2 ** attempt + 2)
    return False
