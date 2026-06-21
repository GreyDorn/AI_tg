from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import DAILY_FREE_CREDITS, REFERRAL_BONUS_CREDITS, FREE_CREDITS_ON_START
from db.models import User
from db.repository import claim_daily_credits
from bot.keyboards.main import referral_keyboard

router = Router()


@router.message(Command("balance"))
@router.message(F.text == "💰 Баланс")
async def cmd_balance(message: Message, db_session: AsyncSession, db_user: User) -> None:
    # Попробуем начислить ежедневные кредиты
    got_daily = await claim_daily_credits(db_session, db_user.id)
    await db_session.refresh(db_user)

    daily_line = f"\n✅ <b>+{DAILY_FREE_CREDITS}🔥 ежедневный бонус получен!</b>" if got_daily else ""

    await message.answer(
        f"💰 <b>Твой баланс</b>\n\n"
        f"🔥 <b>{db_user.credits} кредитов</b>{daily_line}\n\n"
        f"<b>Как получить кредиты бесплатно:</b>\n"
        f"• {DAILY_FREE_CREDITS}🔥 каждый день (приходи ежедневно!)\n"
        f"• {REFERRAL_BONUS_CREDITS}🔥 за каждого приглашённого друга (/referral)\n\n"
        f"<i>Скоро: пополнение через Telegram Stars ⭐</i>",
        parse_mode="HTML",
    )


@router.message(Command("referral"))
@router.message(F.text == "👥 Реферал")
async def cmd_referral(message: Message, db_user: User, bot) -> None:
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref{db_user.id}"

    await message.answer(
        f"👥 <b>Реферальная программа</b>\n\n"
        f"Приглашай друзей — получай кредиты!\n\n"
        f"За каждого нового пользователя по твоей ссылке:\n"
        f"• Тебе: <b>+{REFERRAL_BONUS_CREDITS}🔥</b>\n"
        f"• Другу: <b>+{FREE_CREDITS_ON_START}🔥</b> (стандартный стартовый бонус)\n\n"
        f"🔗 <b>Твоя ссылка:</b>\n"
        f"<code>{ref_link}</code>",
        parse_mode="HTML",
        reply_markup=referral_keyboard(bot_info.username, db_user.id),
    )
