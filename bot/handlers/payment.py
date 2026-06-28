import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, LabeledPrice,
    PreCheckoutQuery, SuccessfulPayment,
)
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from config import SUBSCRIPTION_PRICE_STARS, SUBSCRIPTION_DAYS, PREMIUM_BOT_STARS_URL, RATE_LIMIT_MESSAGES, RATE_LIMIT_WINDOW
from db.models import User
from db.repository import process_subscription_payment
from bot.keyboards.main import subscription_keyboard
from bot.i18n import t, button_filter

router = Router()
logger = logging.getLogger(__name__)

SUBSCRIPTION_PAYLOAD_PREFIX = "subscription:"
SUBSCRIPTION_START_PARAMETER = "unlimited_sub"


def _subscription_payload(user_id: int) -> str:
    return f"{SUBSCRIPTION_PAYLOAD_PREFIX}{user_id}"


def _is_subscription_payload(payload: str, user_id: int) -> bool:
    return payload == _subscription_payload(user_id)


@router.message(Command("buy"))
@router.message(button_filter("subscription"))
async def cmd_buy(message: Message, db_user: User, lang: str = "en") -> None:
    sub_status = ""
    if db_user.has_unlimited_access and db_user.subscription_until:
        sub_status = t(
            "buy_sub_active",
            lang,
            date=db_user.subscription_until.strftime("%d.%m.%Y"),
            days=SUBSCRIPTION_DAYS,
        )

    await message.answer(
        t(
            "buy_info",
            lang,
            days=SUBSCRIPTION_DAYS,
            sub_status=sub_status,
            rate_limit=RATE_LIMIT_MESSAGES,
            rate_window=RATE_LIMIT_WINDOW,
            price=SUBSCRIPTION_PRICE_STARS,
        ),
        reply_markup=subscription_keyboard(lang),
    )


@router.callback_query(F.data == "subscribe")
async def process_subscribe_callback(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Message not found. Try /buy again.", show_alert=True)
        return

    user_id = callback.from_user.id
    try:
        await callback.message.answer_invoice(
            title="Unlimited Subscription — 30 days",
            description=(
                f"Unlimited text + image requests to all models for {SUBSCRIPTION_DAYS} days. "
                f"Fair-use: {RATE_LIMIT_MESSAGES} messages per {RATE_LIMIT_WINDOW} sec."
            ),
            payload=_subscription_payload(user_id),
            currency="XTR",
            prices=[
                LabeledPrice(
                    label=f"{SUBSCRIPTION_DAYS}-day Subscription",
                    amount=SUBSCRIPTION_PRICE_STARS,
                )
            ],
            start_parameter=SUBSCRIPTION_START_PARAMETER,
        )
    except TelegramAPIError as exc:
        logger.exception("Failed to send Stars invoice for user=%s", user_id)
        await callback.answer(
            "Failed to create payment. Please try again later.",
            show_alert=True,
        )
        await callback.message.answer(
            "❌ <b>Payment could not be started.</b>\n\n"
            "If the error persists:\n"
            "1. Make sure you have enough ⭐ on your balance "
            f"(need {SUBSCRIPTION_PRICE_STARS} ⭐)\n"
            "2. Tap <b>Buy Stars</b> in /buy to top up via PremiumBot\n"
            "3. Write to /paysupport\n\n"
            f"<i>Technical details: {exc.message}</i>",
        )
        return

    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    if not _is_subscription_payload(query.invoice_payload, query.from_user.id):
        await query.answer(
            ok=False,
            error_message="Invalid order. Please start again with /buy.",
        )
        return

    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(
    message: Message, db_session: AsyncSession, db_user: User, lang: str = "en"
) -> None:
    payment: SuccessfulPayment = message.successful_payment

    if not _is_subscription_payload(payment.invoice_payload, message.from_user.id):
        logger.warning(
            "Unexpected payment payload: user=%s payload=%s",
            message.from_user.id,
            payment.invoice_payload,
        )
        await message.answer(
            "Payment received, but the order could not be identified. "
            "Please contact /paysupport."
        )
        return

    charge_id = payment.telegram_payment_charge_id
    result = await process_subscription_payment(
        db_session,
        user_id=db_user.id,
        charge_id=charge_id,
        amount=payment.total_amount,
        payload=payment.invoice_payload,
        days=SUBSCRIPTION_DAYS,
    )

    if not result.subscription_until:
        logger.error("Subscription payment failed: user=%s charge_id=%s", db_user.id, charge_id)
        await message.answer(
            "Payment received, but subscription could not be activated. "
            "Please contact /paysupport."
        )
        return

    logger.info(
        "Subscription: user=%s until=%s charge_id=%s duplicate=%s",
        db_user.id, result.subscription_until, charge_id, result.is_duplicate,
    )

    until_text = result.subscription_until.strftime("%d.%m.%Y")
    if result.is_duplicate:
        await message.answer(
            t("sub_already_paid", lang, date=until_text),
            parse_mode="HTML",
        )
        return

    await message.answer(
        t("sub_activated", lang, date=until_text),
        parse_mode="HTML",
    )


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message) -> None:
    await message.answer(
        "💬 <b>Payment Support</b>\n\n"
        "If you have issues paying with Telegram Stars:\n\n"
        f"1. You need at least <b>{SUBSCRIPTION_PRICE_STARS} ⭐</b> on your balance\n"
        "2. Open /buy and tap <b>Buy Stars</b> — PremiumBot opens inline\n"
        f"3. Alternative link: {PREMIUM_BOT_STARS_URL}\n"
        "4. If you see <code>PROVIDER_ACCOUNT_INVALID</code>, "
        "try another card or Telegram Desktop\n"
        "5. After buying stars, tap <b>Subscribe</b> in /buy\n\n"
        "If the problem persists, describe the error and send a screenshot here. "
        "We will help manually.",
    )
