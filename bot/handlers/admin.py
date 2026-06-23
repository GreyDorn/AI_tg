from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import ADMIN_ID, OPENROUTER_PROBE_INTERVAL
from db.models import User
from db.repository import grant_unlimited, get_user, get_bot_stats
from llm.provider_status import get_openrouter_status, OPENROUTER_CREDITS_URL

router = Router()


@router.message(Command("stats"))
async def cmd_stats(message: Message, db_session: AsyncSession, db_user: User) -> None:
    if db_user.id != ADMIN_ID:
        return

    stats = await get_bot_stats(db_session)
    await message.answer(
        "📊 <b>Bot statistics</b>\n\n"
        f"<b>Users</b>\n"
        f"• Total: <b>{stats.total_users}</b>\n"
        f"• New today: <b>{stats.new_today}</b>\n"
        f"• New (7 days): <b>{stats.new_7d}</b>\n"
        f"• Active (7 days): <b>{stats.active_users_7d}</b>\n"
        f"• Subscribers: <b>{stats.active_subscribers}</b>\n"
        f"• Unlimited: <b>{stats.unlimited_users}</b>\n\n"
        f"<b>Messages</b>\n"
        f"• Total user messages: <b>{stats.total_user_messages}</b>\n"
        f"• Today: <b>{stats.messages_today}</b>\n\n"
        f"<b>Payments (Stars)</b>\n"
        f"• All time: <b>{stats.payments_total}</b> payments, <b>{stats.stars_total}</b> ⭐\n"
        f"• Last 30 days: <b>{stats.payments_30d}</b> payments, <b>{stats.stars_30d}</b> ⭐",
        parse_mode="HTML",
    )


@router.message(Command("openrouter"))
async def cmd_openrouter(message: Message, db_user: User) -> None:
    if db_user.id != ADMIN_ID:
        return

    status = await get_openrouter_status(force_probe=True)
    if not status.configured:
        await message.answer(
            "⚠️ <b>OpenRouter is not configured</b>\n\n"
            "Set <code>OPENROUTER_API_KEY</code> in <code>.env</code> on the server.",
            parse_mode="HTML",
        )
        return

    lines = ["💳 <b>OpenRouter status</b>\n"]
    if status.paid_available:
        lines.append("• Paid models: <b>available</b> ✅")
    else:
        lines.append("• Paid models: <b>hidden</b> (no credits) ❌")

    if status.limit_remaining is not None:
        lines.append(f"• Balance remaining: <b>${status.limit_remaining:.4f}</b>")
    if status.usage is not None:
        lines.append(f"• Total usage: <b>${status.usage:.4f}</b>")
    if status.is_free_tier is not None:
        lines.append(f"• Free tier only: <b>{'yes' if status.is_free_tier else 'no'}</b>")

    if status.needs_topup:
        lines.append(
            f"\nTop up credits here:\n<a href=\"{OPENROUTER_CREDITS_URL}\">{OPENROUTER_CREDITS_URL}</a>\n\n"
            "After payment, paid image models appear automatically within "
            f"{OPENROUTER_PROBE_INTERVAL // 60} min (or restart the bot)."
        )
    else:
        lines.append("\nGemini Image and Flux Klein are available in /imagemodels.")

    if status.error:
        lines.append(f"\n<i>{status.error}</i>")

    await message.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("grant"))
async def cmd_grant(message: Message, db_session: AsyncSession, db_user: User) -> None:
    if db_user.id != ADMIN_ID:
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer(
            "Usage: <code>/grant USER_ID</code>\n\n"
            "Example: <code>/grant 123456789</code>",
            parse_mode="HTML",
        )
        return

    target_id = int(parts[1].strip())
    success = await grant_unlimited(db_session, target_id)

    if success:
        target = await get_user(db_session, target_id)
        name = target.full_name if target else str(target_id)
        await message.answer(
            f"✅ Unlimited access granted to <b>{name}</b> (ID: <code>{target_id}</code>)",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"❌ User <code>{target_id}</code> not found.\n"
            f"They need to start the bot first with /start.",
            parse_mode="HTML",
        )
