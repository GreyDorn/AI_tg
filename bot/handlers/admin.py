from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import ADMIN_ID
from db.models import User
from db.repository import grant_unlimited, get_user, get_bot_stats

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
