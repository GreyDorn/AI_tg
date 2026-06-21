from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import ADMIN_ID
from db.models import User
from db.repository import grant_unlimited, get_user

router = Router()


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
