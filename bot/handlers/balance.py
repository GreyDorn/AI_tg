from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import REFERRAL_BONUS_CREDITS
from db.models import User
from db.repository import claim_daily_credits
from bot.keyboards.main import referral_keyboard, growth_keyboard
from bot.utils.growth import balance_free_tier_text, referral_link, referral_program_text

router = Router()


@router.message(Command("balance"))
@router.message(F.text == "💰 Balance")
async def cmd_balance(message: Message, db_session: AsyncSession, db_user: User) -> None:
    got_daily = await claim_daily_credits(db_session, db_user.id)
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
            balance_free_tier_text(db_user.credits, got_daily),
            parse_mode="HTML",
            reply_markup=growth_keyboard(bot_info.username, db_user.id),
        )


@router.message(Command("referral"))
@router.message(F.text == "👥 Referral")
async def cmd_referral(message: Message, db_user: User, bot) -> None:
    bot_info = await bot.get_me()
    ref_link = referral_link(bot_info.username, db_user.id)

    await message.answer(
        referral_program_text(ref_link),
        parse_mode="HTML",
        reply_markup=referral_keyboard(bot_info.username, db_user.id),
    )
