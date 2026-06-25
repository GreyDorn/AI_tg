from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import REFERRAL_BONUS_CREDITS
from db.models import User
from db.repository import claim_daily_credits
from bot.keyboards.main import referral_keyboard, growth_keyboard
from bot.utils.growth import balance_free_tier_text

router = Router()


@router.message(Command("balance"))
@router.message(F.text == "💰 Balance")
async def cmd_balance(message: Message, db_session: AsyncSession, db_user: User) -> None:
    got_daily, streak_bonus = await claim_daily_credits(db_session, db_user.id)
    await db_session.refresh(db_user)

    if db_user.has_unlimited_access:
        if db_user.is_unlimited:
            status = "✨ <b>Unlimited access</b> (permanent)"
        else:
            status = f"✨ <b>Subscription active</b> until <b>{db_user.subscription_until.strftime('%d.%m.%Y')}</b>"
        await message.answer(
            f"💰 <b>Your Balance</b>\n\n"
            f"{status}\n\n"
            f"Requests: <b>unlimited</b>\n\n"
            f"👥 Invite friends — still earn <b>+{REFERRAL_BONUS_CREDITS}</b> per signup",
            parse_mode="HTML",
            reply_markup=referral_keyboard(
                (await message.bot.get_me()).username,
                db_user.id,
            ),
        )
    else:
        bot_info = await message.bot.get_me()
        await message.answer(
            balance_free_tier_text(
                db_user.credits, got_daily, streak_bonus, db_user.login_streak,
            ),
            parse_mode="HTML",
            reply_markup=growth_keyboard(bot_info.username, db_user.id),
        )
