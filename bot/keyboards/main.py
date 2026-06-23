from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import MODELS, DEFAULT_MODEL, SUBSCRIPTION_PRICE_STARS, STARS_TOPUP_URL
from llm.provider_status import get_available_image_models, get_available_music_models
from llm.music_gen import is_music_feature_enabled


def main_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="💬 New Chat"), KeyboardButton(text="🤖 Models")],
        [KeyboardButton(text="🎨 Create Image"), KeyboardButton(text="🖼 Image Models")],
    ]
    if is_music_feature_enabled():
        keyboard.append(
            [KeyboardButton(text="🎵 Create Music"), KeyboardButton(text="🎵 Music Models")]
        )
    keyboard.extend([
        [KeyboardButton(text="💰 Balance"), KeyboardButton(text="👥 Referral")],
        [KeyboardButton(text="💎 Subscription")],
    ])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def models_keyboard(current_model: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, model in MODELS.items():
        mark = "✅ " if key == current_model else ""
        vision = " 📷" if model.supports_vision else ""
        builder.button(
            text=f"{mark}{model.name}{vision}",
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


def music_models_keyboard(current_model: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, model in get_available_music_models().items():
        mark = "✅ " if key == current_model else ""
        cost = "free" if model.cost_per_track == 0 else f"{model.cost_per_track} req"
        builder.button(
            text=f"{mark}{model.name} ({cost})",
            callback_data=f"musicmodel:{key}",
        )
    builder.adjust(1)
    return builder.as_markup()


def cancel_music_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_music")]]
    )


def referral_keyboard(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    ref_link = f"https://t.me/{bot_username}?start=ref{user_id}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Share Link", url=f"https://t.me/share/url?url={ref_link}&text=Try%20this%20AI%20bot!")]
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
