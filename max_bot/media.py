"""Download media from MAX attachment URLs."""

from __future__ import annotations

import logging

import aiohttp

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 4 * 1024 * 1024


def find_image_url(attachments: list[dict]) -> tuple[str | None, str]:
    for att in attachments:
        att_type = (att.get("type") or "").lower()
        if att_type not in ("image", "photo", "picture"):
            continue
        payload = att.get("payload") or {}
        url = payload.get("url")
        if url:
            mime = str(payload.get("mime_type") or payload.get("mime") or "image/jpeg")
            return str(url), mime
    return None, "image/jpeg"


async def download_bytes(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            resp.raise_for_status()
            data = await resp.read()
            if len(data) > MAX_IMAGE_BYTES:
                raise ValueError("IMAGE_TOO_LARGE")
            return data
