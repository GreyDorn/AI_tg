from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import MODELS, DEFAULT_MODEL, SUBSCRIPTION_PRICE_STARS, STARS_TOPUP_URL
from llm.provider_status import get_available_image_models


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💬 New Chat"), KeyboardButton(text="🤖 Models")],
            [KeyboardButton(text="🎨 Create Image"), KeyboardButton(text="🖼 Image Models")],
            [KeyboardButton(text="💰 Balance"), KeyboardButton(text="👥 Referral")],
            [KeyboardButton(text="💎 Subscription")],
        ],
        resize_keyboard=True,
    )


def models_keyboard(current_model: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, model in MODELS.items():
        mark = "✅ " if key == current_model else ""
        builder.button(
            text=f"{mark}{model.name}",
            callback_data=f"model:{key}",
        )
    builder.adjust(1)
    return builder.as_markup()


def image_models_keyboard(current_model: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, model in get_available_image_models().items():
        mark = "✅ " if key == current_model else ""
        cost = "free" if model.cost_per_image == 0 else f"{model.cost_per_image} req"
        builder.button(
            text=f"{mark}{model.name} ({cost})",
            callback_data=f"imagemodel:{key}",
        )
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")]]
    )


def referral_keyboard(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    from bot.utils.growth import share_url

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Share bot", url=share_url(bot_username, user_id))],
            [InlineKeyboardButton(
                text=f"💎 Subscribe — {SUBSCRIPTION_PRICE_STARS} ⭐",
                callback_data="subscribe",
            )],
        ]
    )


def growth_keyboard(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    from bot.utils.growth import share_url

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Share bot (+3 req)", url=share_url(bot_username, user_id))],
            [InlineKeyboardButton(
                text=f"💎 Subscribe — {SUBSCRIPTION_PRICE_STARS} ⭐",
                callback_data="subscribe",
            )],
        ]
    )


def subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"Buy Stars — from {SUBSCRIPTION_PRICE_STARS} ⭐",
                url=STARS_TOPUP_URL,
            )],
            [InlineKeyboardButton(
                text=f"Subscribe — {SUBSCRIPTION_PRICE_STARS} ⭐",
                callback_data="subscribe",
            )],
        ]
    )
