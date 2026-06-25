import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User
from db.repository import count_referrals, get_referral_leaderboard
from bot.keyboards.main import growth_keyboard
from bot.utils.growth import referral_link, invite_dashboard_text, leaderboard_text

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("invite", "referral"))
@router.message(F.text == "👥 Referral")
async def cmd_invite(message: Message, db_session: AsyncSession, db_user: User) -> None:
    bot_info = await message.bot.get_me()
    ref_count = await count_referrals(db_session, db_user.id)
    ref_link = referral_link(bot_info.username, db_user.id)

    await message.answer(
        invite_dashboard_text(
            ref_link,
            ref_count,
            db_user.credits,
            db_user.login_streak,
        ),
        parse_mode="HTML",
        reply_markup=growth_keyboard(bot_info.username, db_user.id),
    )


@router.message(Command("top"))
async def cmd_top(message: Message, db_session: AsyncSession) -> None:
    bot_info = await message.bot.get_me()
    entries = await get_referral_leaderboard(db_session, limit=10)
    await message.answer(
        leaderboard_text(entries, bot_info.username),
        parse_mode="HTML",
    )
