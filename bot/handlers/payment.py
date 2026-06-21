import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, LabeledPrice,
    PreCheckoutQuery, SuccessfulPayment,
)
from sqlalchemy.ext.asyncio import AsyncSession
from config import SUBSCRIPTION_PRICE_STARS, SUBSCRIPTION_DAYS
from db.models import User
from db.repository import activate_subscription
from bot.keyboards.main import subscription_keyboard

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("buy"))
@router.message(F.text == "💎 Подписка")
async def cmd_buy(message: Message, db_user: User) -> None:
    sub_status = ""
    if db_user.has_unlimited_access and db_user.subscription_until:
        sub_status = f"\n\n✨ <b>Твоя подписка активна</b> до <b>{db_user.subscription_until.strftime('%d.%m.%Y')}</b>\nПри оплате — продлится ещё на {SUBSCRIPTION_DAYS} дней."

    await message.answer(
        f"💎 <b>Безлимитная подписка</b>\n\n"
        f"• Неограниченное количество запросов\n"
        f"• Все модели без ограничений\n"
        f"• {SUBSCRIPTION_DAYS} дней доступа{sub_status}\n\n"
        f"Стоимость: <b>{SUBSCRIPTION_PRICE_STARS} ⭐ Stars / месяц</b>",
        reply_markup=subscription_keyboard(),
    )


@router.callback_query(F.data == "subscribe")
async def process_subscribe_callback(callback: CallbackQuery) -> None:
    await callback.message.answer_invoice(
        title="Безлимитная подписка на 30 дней",
        description=f"Неограниченные запросы ко всем AI-моделям на {SUBSCRIPTION_DAYS} дней",
        payload=f"subscription:{callback.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"Подписка {SUBSCRIPTION_DAYS} дней", amount=SUBSCRIPTION_PRICE_STARS)],
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
    charge_id = payment.telegram_payment_charge_id

    subscription_until = await activate_subscription(db_session, db_user.id, SUBSCRIPTION_DAYS)

    logger.info(
        "Подписка: user=%s до %s charge_id=%s",
        db_user.id, subscription_until, charge_id,
    )

    await message.answer(
        f"✅ <b>Подписка активирована!</b>\n\n"
        f"Безлимитный доступ ко всем моделям до <b>{subscription_until.strftime('%d.%m.%Y')}</b> 🎉",
    )
