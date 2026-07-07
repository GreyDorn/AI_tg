"""MAX messenger bot — webhook on RU VPS, LLM via DE gateway."""

from __future__ import annotations

import asyncio
import hmac
import logging
import sys
from collections import OrderedDict

from aiohttp import web

from config import MAX_BOT_PORT, MAX_WEBHOOK_SECRET
from db.repository import init_db
from max_bot.handlers import process_update

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

_seen: OrderedDict[str, None] = OrderedDict()
_seen_max = 500


def _remember_event(key: str | None) -> bool:
    if not key:
        return False
    if key in _seen:
        return True
    _seen[key] = None
    while len(_seen) > _seen_max:
        _seen.popitem(last=False)
    return False


def _event_key(update: dict) -> str | None:
    update_type = update.get("update_type") or "unknown"
    message = update.get("message") or {}
    body = message.get("body") or {}
    mid = body.get("mid")
    if mid:
        return f"{update_type}:{mid}"
    callback = update.get("callback") or {}
    callback_id = callback.get("callback_id")
    if callback_id:
        return f"{update_type}:{callback_id}"
    ts = update.get("timestamp")
    return f"{update_type}:{ts}" if ts is not None else None


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def webhook(request: web.Request) -> web.Response:
    if request.method == "HEAD":
        return web.Response(status=200)

    if MAX_WEBHOOK_SECRET:
        got = request.headers.get("X-Max-Bot-Api-Secret", "")
        if not hmac.compare_digest(got, MAX_WEBHOOK_SECRET):
            return web.json_response({"error": "forbidden"}, status=403)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": True})

    if not isinstance(data, dict):
        return web.json_response({"ok": True})

    key = _event_key(data)
    if _remember_event(key):
        return web.json_response({"ok": True, "duplicate": True})

    asyncio.create_task(_process_safe(data))
    return web.json_response({"ok": True})


async def _process_safe(update: dict) -> None:
    try:
        await process_update(update)
    except Exception:
        logger.exception("Error processing MAX update")


def create_app() -> web.Application:
    app = web.Application(client_max_size=20 * 1024 * 1024)
    app.router.add_get("/health", health)
    app.router.add_route("*", "/webhook", webhook)
    return app


async def main() -> None:
    await init_db()
    logger.info("MAX bot database initialized")

    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", MAX_BOT_PORT)
    await site.start()
    logger.info("MAX bot webhook listening on 0.0.0.0:%s", MAX_BOT_PORT)

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
