"""Admin commands for MAX bot."""

from __future__ import annotations

import logging
import re

from config import MAX_ADMIN_ID, MONETIZATION_ENABLED
from db.repository import SessionFactory, get_bot_stats
from max_bot.api import send_message
from max_bot.gateway_client import fetch_provider_limits

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def is_max_admin(user_id: int) -> bool:
    return MAX_ADMIN_ID > 0 and user_id == MAX_ADMIN_ID


def _strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub("", text).replace("&nbsp;", " ").strip()


def _build_stats_text(stats) -> str:
    lines = [
        "📊 Статистика MAX-бота",
        "",
        "Пользователи",
        f"• Всего: {stats.total_users}",
        f"• Новых сегодня: {stats.new_today}",
        f"• Новых за 7 дней: {stats.new_7d}",
        f"• Активных за 7 дней: {stats.active_users_7d}",
        f"• С подпиской: {stats.active_subscribers}",
        f"• Безлимит: {stats.unlimited_users}",
        "",
        "Сообщения",
        f"• Всего от пользователей: {stats.total_user_messages}",
        f"• Сегодня: {stats.messages_today}",
    ]

    if MONETIZATION_ENABLED:
        lines.extend([
            "",
            "Платежи (Stars)",
            f"• Всего: {stats.payments_total} платежей, {stats.stars_total} ⭐",
            f"• За 30 дней: {stats.payments_30d} платежей, {stats.stars_30d} ⭐",
        ])

    return "\n".join(lines)


async def handle_stats(user_id: int) -> None:
    if not MAX_ADMIN_ID:
        await send_message(
            user_id=user_id,
            text=(
                "MAX_ADMIN_ID не задан на сервере.\n\n"
                f"Ваш MAX user_id: {user_id}\n"
                "Добавьте его в .env как MAX_ADMIN_ID и перезапустите бота."
            ),
        )
        return

    if not is_max_admin(user_id):
        return

    async with SessionFactory() as session:
        stats = await get_bot_stats(session)

    text = _build_stats_text(stats)

    limits = await fetch_provider_limits()
    if limits:
        text = f"{text}\n\n{_strip_html(limits)}"

    await send_message(user_id=user_id, text=text[:4000])
