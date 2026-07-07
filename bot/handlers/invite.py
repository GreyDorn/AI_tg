import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import MONETIZATION_ENABLED
from db.models import User
from db.repository import count_referrals, get_referral_leaderboard
from bot.keyboards.main import growth_keyboard
from bot.i18n import button_filter
from bot.utils.growth import referral_link, invite_dashboard_text, leaderboard_text

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("invite", "referral"))
@router.message(button_filter("referral"))
async def cmd_invite(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    lang: str = "en",
) -> None:
    if not MONETIZATION_ENABLED:
        return

    bot_info = await message.bot.get_me()
    ref_count = await count_referrals(db_session, db_user.id)
    ref_link = referral_link(bot_info.username, db_user.id)

    await message.answer(
        invite_dashboard_text(
            ref_link,
            ref_count,
            db_user.credits,
            db_user.login_streak,
            lang,
        ),
        parse_mode="HTML",
        reply_markup=growth_keyboard(bot_info.username, db_user.id, lang),
    )


@router.message(Command("top"))
async def cmd_top(message: Message, db_session: AsyncSession, lang: str = "en") -> None:
    if not MONETIZATION_ENABLED:
        return

    bot_info = await message.bot.get_me()
    entries = await get_referral_leaderboard(db_session, limit=10)
    await message.answer(
        leaderboard_text(entries, bot_info.username, lang),
        parse_mode="HTML",
    )
