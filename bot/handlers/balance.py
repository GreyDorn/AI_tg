from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from config import REFERRAL_BONUS_CREDITS, DAILY_FREE_CREDITS, MONETIZATION_ENABLED
from db.models import User
from db.repository import claim_daily_credits
from bot.keyboards.main import referral_keyboard, growth_keyboard
from bot.i18n import t, button_filter
from bot.utils.growth import balance_free_tier_text

router = Router()


async def _send_balance(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    *,
    got_daily: bool,
    streak_bonus: int,
    lang: str,
) -> None:
    await db_session.refresh(db_user)
    if db_user.has_unlimited_access:
        if db_user.is_unlimited:
            status = t("balance_unlimited_perm", lang)
        else:
            status = t(
                "balance_unlimited_sub",
                lang,
                date=db_user.subscription_until.strftime("%d.%m.%Y"),
            )
        await message.answer(
            t("balance_unlimited_body", lang, status=status, bonus=REFERRAL_BONUS_CREDITS),
            parse_mode="HTML",
            reply_markup=referral_keyboard(
                (await message.bot.get_me()).username,
                db_user.id,
                lang,
            ),
        )
    else:
        bot_info = await message.bot.get_me()
        await message.answer(
            balance_free_tier_text(
                db_user.credits, got_daily, streak_bonus, db_user.login_streak, lang,
            ),
            parse_mode="HTML",
            reply_markup=growth_keyboard(bot_info.username, db_user.id, lang),
        )


@router.message(Command("balance"))
@router.message(button_filter("balance"))
async def cmd_balance(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    lang: str = "en",
) -> None:
    if not MONETIZATION_ENABLED:
        return
    got_daily, streak_bonus = await claim_daily_credits(db_session, db_user.id)
    await _send_balance(message, db_session, db_user, got_daily=got_daily, streak_bonus=streak_bonus, lang=lang)


@router.callback_query(F.data == "claim_daily")
async def claim_daily_callback(
    callback: CallbackQuery,
    db_session: AsyncSession,
    db_user: User,
    lang: str = "en",
) -> None:
    if not MONETIZATION_ENABLED:
        return
    if db_user.has_unlimited_access:
        await callback.answer(t("claim_already_unlimited", lang), show_alert=True)
        return

    got_daily, streak_bonus = await claim_daily_credits(db_session, db_user.id)
    if not got_daily:
        await callback.answer(t("claim_already_today", lang), show_alert=True)
        return

    bonus_part = f" (+{streak_bonus} 🔥)" if streak_bonus else ""
    await callback.answer(
        t("claim_added", lang, daily=DAILY_FREE_CREDITS, bonus_part=bonus_part),
        show_alert=True,
    )

    if callback.message:
        await db_session.refresh(db_user)
        bot_info = await callback.message.bot.get_me()
        await callback.message.answer(
            balance_free_tier_text(
                db_user.credits, True, streak_bonus, db_user.login_streak, lang,
            ),
            parse_mode="HTML",
            reply_markup=growth_keyboard(bot_info.username, db_user.id, lang),
        )
