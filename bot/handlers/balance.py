from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import DAILY_FREE_CREDITS, REFERRAL_BONUS_CREDITS, FREE_CREDITS_ON_START, SUBSCRIPTION_PRICE_STARS
from db.models import User
from db.repository import claim_daily_credits
from bot.keyboards.main import referral_keyboard

router = Router()


@router.message(Command("balance"))
@router.message(F.text == "💰 Balance")
async def cmd_balance(message: Message, db_session: AsyncSession, db_user: User) -> None:
    got_daily = await claim_daily_credits(db_session, db_user.id)
    await db_session.refresh(db_user)

    daily_line = f"\n✅ <b>+{DAILY_FREE_CREDITS} daily requests added!</b>" if got_daily else ""

    if db_user.has_unlimited_access:
        if db_user.is_unlimited:
            status = "✨ <b>Unlimited access</b> (permanent)"
        else:
            status = f"✨ <b>Subscription active</b> until <b>{db_user.subscription_until.strftime('%d.%m.%Y')}</b>"
        await message.answer(
            f"💰 <b>Your Balance</b>\n\n"
            f"{status}\n\n"
            f"Requests: <b>unlimited</b>",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"💰 <b>Your Balance</b>\n\n"
            f"Requests: <b>{db_user.credits}</b>{daily_line}\n\n"
            f"<b>Get free requests:</b>\n"
            f"• +{DAILY_FREE_CREDITS} every day (come back daily!)\n"
            f"• +{REFERRAL_BONUS_CREDITS} for each referred friend (/referral)\n\n"
            f"💎 <b>Unlimited subscription</b> — {SUBSCRIPTION_PRICE_STARS} ⭐/month → /buy",
            parse_mode="HTML",
        )


@router.message(Command("referral"))
@router.message(F.text == "👥 Referral")
async def cmd_referral(message: Message, db_user: User, bot) -> None:
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref{db_user.id}"

    await message.answer(
        f"👥 <b>Referral Program</b>\n\n"
        f"Invite friends — earn bonus requests!\n\n"
        f"For each new user who joins via your link:\n"
        f"• You get: <b>+{REFERRAL_BONUS_CREDITS} requests</b>\n"
        f"• Your friend gets: <b>+{FREE_CREDITS_ON_START} requests</b> (welcome bonus)\n\n"
        f"🔗 <b>Your referral link:</b>\n"
        f"<code>{ref_link}</code>",
        parse_mode="HTML",
        reply_markup=referral_keyboard(bot_info.username, db_user.id),
    )
