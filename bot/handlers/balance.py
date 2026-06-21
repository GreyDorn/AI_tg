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
@router.message(F.text == "💰 Баланс")
async def cmd_balance(message: Message, db_session: AsyncSession, db_user: User) -> None:
    got_daily = await claim_daily_credits(db_session, db_user.id)
    await db_session.refresh(db_user)

    daily_line = f"\n✅ <b>+{DAILY_FREE_CREDITS} бесплатных запроса получено!</b>" if got_daily else ""

    if db_user.has_unlimited_access:
        if db_user.is_unlimited:
            status = "✨ <b>Безлимитный доступ</b> (постоянный)"
        else:
            status = f"✨ <b>Подписка активна</b> до <b>{db_user.subscription_until.strftime('%d.%m.%Y')}</b>"
        await message.answer(
            f"💰 <b>Твой баланс</b>\n\n"
            f"{status}\n\n"
            f"Запросов: <b>неограничено</b>",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"💰 <b>Твой баланс</b>\n\n"
            f"Запросов: <b>{db_user.credits}</b>{daily_line}\n\n"
            f"<b>Как получить бесплатно:</b>\n"
            f"• +{DAILY_FREE_CREDITS} каждый день (приходи ежедневно!)\n"
            f"• +{REFERRAL_BONUS_CREDITS} за каждого приглашённого друга (/referral)\n\n"
            f"💎 <b>Безлимитная подписка</b> — {SUBSCRIPTION_PRICE_STARS} ⭐/месяц → /buy",
            parse_mode="HTML",
        )


@router.message(Command("referral"))
@router.message(F.text == "👥 Реферал")
async def cmd_referral(message: Message, db_user: User, bot) -> None:
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref{db_user.id}"

    await message.answer(
        f"👥 <b>Реферальная программа</b>\n\n"
        f"Приглашай друзей — получай бонусные запросы!\n\n"
        f"За каждого нового пользователя по твоей ссылке:\n"
        f"• Тебе: <b>+{REFERRAL_BONUS_CREDITS} запроса</b>\n"
        f"• Другу: <b>+{FREE_CREDITS_ON_START} запросов</b> (стартовый бонус)\n\n"
        f"🔗 <b>Твоя ссылка:</b>\n"
        f"<code>{ref_link}</code>",
        parse_mode="HTML",
        reply_markup=referral_keyboard(bot_info.username, db_user.id),
    )
