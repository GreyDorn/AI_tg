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
@router.message(F.text == "💎 Subscription")
async def cmd_buy(message: Message, db_user: User) -> None:
    sub_status = ""
    if db_user.has_unlimited_access and db_user.subscription_until:
        sub_status = f"\n\n✨ <b>Your subscription is active</b> until <b>{db_user.subscription_until.strftime('%d.%m.%Y')}</b>\nA new payment will extend it by {SUBSCRIPTION_DAYS} more days."

    await message.answer(
        f"💎 <b>Unlimited Subscription</b>\n\n"
        f"• Unlimited requests to all models\n"
        f"• All models, no restrictions\n"
        f"• {SUBSCRIPTION_DAYS} days of access{sub_status}\n\n"
        f"Price: <b>{SUBSCRIPTION_PRICE_STARS} ⭐ Stars / month</b>",
        reply_markup=subscription_keyboard(),
    )


@router.callback_query(F.data == "subscribe")
async def process_subscribe_callback(callback: CallbackQuery) -> None:
    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Unlimited Subscription — 30 days",
        description=f"Unlimited requests to all AI models for {SUBSCRIPTION_DAYS} days",
        payload=f"subscription:{callback.from_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{SUBSCRIPTION_DAYS}-day Subscription", amount=SUBSCRIPTION_PRICE_STARS)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(
    message: Message, db_session: AsyncSession, db_user: User
) -> None:
    payment: SuccessfulPayment = message.successful_payment
    charge_id = payment.telegram_payment_charge_id

    subscription_until = await activate_subscription(db_session, db_user.id, SUBSCRIPTION_DAYS)

    logger.info(
        "Subscription: user=%s until=%s charge_id=%s",
        db_user.id, subscription_until, charge_id,
    )

    await message.answer(
        f"✅ <b>Subscription activated!</b>\n\n"
        f"Unlimited access to all models until <b>{subscription_until.strftime('%d.%m.%Y')}</b> 🎉",
    )
