"""Background tasks: daily bonus reminders and promo channel posts."""
import asyncio
import logging
from datetime import datetime, date, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import (
    DAILY_REMINDER_ENABLED,
    DAILY_REMINDER_HOUR_UTC,
    CHANNEL_POST_ENABLED,
    CHANNEL_POST_INTERVAL,
    PROMO_CHANNEL_ID,
    DAILY_FREE_CREDITS,
    REFERRAL_BONUS_CREDITS,
    SUBSCRIPTION_PRICE_STARS,
    STREAK_BONUS_START,
)
from db.repository import SessionFactory, get_users_for_daily_reminder, mark_daily_reminder_sent, get_bot_stats

logger = logging.getLogger(__name__)

_reminder_task: asyncio.Task | None = None
_channel_task: asyncio.Task | None = None
_last_reminder_date: date | None = None
_last_channel_post_at: datetime | None = None


def daily_reminder_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Claim daily bonus", callback_data="claim_daily")],
        ]
    )


def _reminder_text(streak: int) -> str:
    streak_hint = ""
    if streak >= 2:
        streak_hint = f"\n🔥 Streak: <b>{streak} days</b> — don't break it!"
    elif streak == 1:
        streak_hint = "\n🔥 Come back tomorrow to start a streak!"
    return (
        f"🎁 <b>Your daily bonus is ready!</b>\n\n"
        f"Tap below to get <b>+{DAILY_FREE_CREDITS} free requests</b>{streak_hint}\n\n"
        f"Or invite friends → <b>+{REFERRAL_BONUS_CREDITS}</b> each via /invite"
    )


async def send_daily_reminders(bot: Bot) -> int:
    """Send reminders to users who haven't claimed today. Returns count sent."""
    bot_info = await bot.get_me()
    sent = 0
    async with SessionFactory() as session:
        users = await get_users_for_daily_reminder(session)
        for user in users:
            try:
                await bot.send_message(
                    user.id,
                    _reminder_text(user.login_streak),
                    parse_mode="HTML",
                    reply_markup=daily_reminder_keyboard(),
                )
                await mark_daily_reminder_sent(session, user.id)
                sent += 1
                await asyncio.sleep(0.05)
            except TelegramForbiddenError:
                logger.debug("User %s blocked bot — skip reminder", user.id)
            except Exception:
                logger.exception("Failed to send daily reminder to %s", user.id)
    logger.info("Daily reminders sent: %d", sent)
    return sent


def _channel_post_templates(bot_username: str, stats_text: str) -> list[str]:
    link = f"https://t.me/{bot_username}"
    return [
        (
            f"🤖 <b>Free AI assistant in Telegram</b>\n\n"
            f"• ChatGPT-class models (Llama, DeepSeek, Gemini)\n"
            f"• Photo analysis 📷\n"
            f"• Image generation 🎨\n"
            f"• <b>{DAILY_FREE_CREDITS} free requests every day</b>\n\n"
            f"👉 <a href=\"{link}\">@{bot_username}</a>"
        ),
        (
            f"👥 <b>Invite friends — earn free unlimited access</b>\n\n"
            f"• <b>+{REFERRAL_BONUS_CREDITS}</b> requests per friend\n"
            f"• 10 friends → <b>3 days unlimited</b>\n"
            f"• 50 friends → <b>1 month unlimited</b>\n\n"
            f"Start → <a href=\"{link}\">@{bot_username}</a>"
        ),
        (
            f"🎨 <b>Create AI images for free</b>\n\n"
            f"Describe what you want — get a picture in seconds.\n"
            f"Flux, Turbo and more models inside the bot.\n\n"
            f"Try now → <a href=\"{link}\">@{bot_username}</a>"
        ),
        (
            f"💎 <b>Unlimited AI for {SUBSCRIPTION_PRICE_STARS} ⭐/month</b>\n\n"
            f"All text & image models, no daily limits.\n"
            f"Or use free tier: <b>{DAILY_FREE_CREDITS}</b> requests/day "
            f"+ streak bonus from day {STREAK_BONUS_START}.\n\n"
            f"👉 <a href=\"{link}\">@{bot_username}</a>"
        ),
        (
            f"📊 <b>Bot update</b>\n\n"
            f"{stats_text}\n\n"
            f"Join → <a href=\"{link}\">@{bot_username}</a>"
        ),
    ]


async def post_to_channel(bot: Bot, *, template_index: int | None = None) -> bool:
    if not PROMO_CHANNEL_ID:
        logger.warning("PROMO_CHANNEL_ID not set — skip channel post")
        return False

    bot_info = await bot.get_me()
    async with SessionFactory() as session:
        stats = await get_bot_stats(session)
    stats_text = (
        f"Users: <b>{stats.total_users}</b> · "
        f"New today: <b>{stats.new_today}</b> · "
        f"Subscribers: <b>{stats.active_subscribers}</b>"
    )
    templates = _channel_post_templates(bot_info.username, stats_text)
    idx = template_index if template_index is not None else date.today().toordinal() % len(templates)
    text = templates[idx % len(templates)]

    try:
        await bot.send_message(
            PROMO_CHANNEL_ID,
            text,
            parse_mode="HTML",
            disable_web_page_preview=False,
        )
        logger.info("Channel post sent to %s (template %d)", PROMO_CHANNEL_ID, idx)
        return True
    except TelegramBadRequest as exc:
        logger.error("Channel post failed: %s", exc)
        return False


async def _reminder_loop(bot: Bot) -> None:
    global _last_reminder_date
    while True:
        try:
            now = datetime.now(timezone.utc)
            if (
                DAILY_REMINDER_ENABLED
                and now.hour == DAILY_REMINDER_HOUR_UTC
                and _last_reminder_date != now.date()
            ):
                await send_daily_reminders(bot)
                _last_reminder_date = now.date()
        except Exception:
            logger.exception("Daily reminder loop error")
        await asyncio.sleep(300)  # check every 5 min


async def _channel_post_loop(bot: Bot) -> None:
    global _last_channel_post_at
    while True:
        try:
            if CHANNEL_POST_ENABLED and PROMO_CHANNEL_ID:
                now = datetime.now(timezone.utc)
                if _last_channel_post_at is None or (
                    now - _last_channel_post_at
                ).total_seconds() >= CHANNEL_POST_INTERVAL:
                    if await post_to_channel(bot):
                        _last_channel_post_at = now
        except Exception:
            logger.exception("Channel post loop error")
        await asyncio.sleep(600)  # check every 10 min


def start_growth_background_tasks(bot: Bot) -> None:
    global _reminder_task, _channel_task
    if DAILY_REMINDER_ENABLED and (_reminder_task is None or _reminder_task.done()):
        _reminder_task = asyncio.create_task(_reminder_loop(bot))
        logger.info("Daily reminder task started (hour UTC=%s)", DAILY_REMINDER_HOUR_UTC)
    if CHANNEL_POST_ENABLED and PROMO_CHANNEL_ID and (
        _channel_task is None or _channel_task.done()
    ):
        _channel_task = asyncio.create_task(_channel_post_loop(bot))
        logger.info(
            "Channel post task started (channel=%s, interval=%ds)",
            PROMO_CHANNEL_ID,
            CHANNEL_POST_INTERVAL,
        )
