import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, LabeledPrice,
    PreCheckoutQuery, SuccessfulPayment,
)
from sqlalchemy.ext.asyncio import AsyncSession
from config import CREDIT_PACKAGES
from db.models import User
from db.repository import add_credits
from bot.keyboards.main import buy_packages_keyboard

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("buy"))
@router.message(F.text == "💳 Купить кредиты")
async def cmd_buy(message: Message, db_user: User) -> None:
    await message.answer(
        "💳 <b>Купить кредиты</b>\n\n"
        "Кредиты тратятся на запросы к AI.\n"
        "Выбери пакет — оплата в Telegram Stars ⭐:",
        reply_markup=buy_packages_keyboard(),
    )


@router.callback_query(F.data.startswith("buy:"))
async def process_buy_callback(callback: CallbackQuery) -> None:
    pack_id = callback.data.split(":", 1)[1]
    pack = CREDIT_PACKAGES.get(pack_id)
    if not pack:
        await callback.answer("Пакет не найден", show_alert=True)
        return

    stars, credits, label = pack
    await callback.message.answer_invoice(
        title=f"Пакет: {credits} кредитов",
        description=f"Пополнение баланса на {credits} 🔥 кредитов для AI-запросов",
        payload=f"{pack_id}:{callback.from_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label=label, amount=stars)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    """Telegram требует ответить в течение 10 секунд."""
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(
    message: Message, db_session: AsyncSession, db_user: User
) -> None:
    payment: SuccessfulPayment = message.successful_payment
    payload = payment.invoice_payload  # "pack_id:user_id"
    charge_id = payment.telegram_payment_charge_id  # нужен для возврата

    pack_id = payload.split(":")[0]
    pack = CREDIT_PACKAGES.get(pack_id)
    if not pack:
        logger.error("Получен платёж с неизвестным payload: %s", payload)
        return

    stars, credits, label = pack
    new_balance = await add_credits(db_session, db_user.id, credits)

    logger.info(
        "Платёж: user=%s pack=%s stars=%d credits=%d balance=%d charge_id=%s",
        db_user.id, pack_id, stars, credits, new_balance, charge_id,
    )

    await message.answer(
        f"✅ <b>Оплата прошла успешно!</b>\n\n"
        f"Начислено: <b>{credits} 🔥 кредитов</b>\n"
        f"Ваш баланс: <b>{new_balance} 🔥</b>",
    )
