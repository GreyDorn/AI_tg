from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import MODELS, SUBSCRIPTION_PRICE_STARS, STARS_TOPUP_URL
from llm.provider_status import get_available_image_models, get_available_music_models
from llm.music_gen import is_music_feature_enabled
from bot.i18n import btn, inline, format_cost, format_model_cost_suffix, DEFAULT_LANG


def main_menu(lang: str = DEFAULT_LANG) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=btn("new_chat", lang)), KeyboardButton(text=btn("models", lang))],
        [KeyboardButton(text=btn("create_image", lang)), KeyboardButton(text=btn("image_models", lang))],
    ]
    if is_music_feature_enabled():
        keyboard.append(
            [KeyboardButton(text=btn("create_music", lang)), KeyboardButton(text=btn("music_models", lang))]
        )
    from config import MONETIZATION_ENABLED
    if MONETIZATION_ENABLED:
        keyboard.extend([
            [KeyboardButton(text=btn("balance", lang)), KeyboardButton(text=btn("referral", lang))],
            [KeyboardButton(text=btn("subscription", lang))],
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


def image_models_keyboard(current_model: str, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, model in get_available_image_models().items():
        mark = "✅ " if key == current_model else ""
        cost_suffix = format_model_cost_suffix(model.cost_per_image, lang)
        label = f"{mark}{model.name}{cost_suffix}" if cost_suffix else f"{mark}{model.name}"
        builder.button(
            text=label,
            callback_data=f"imagemodel:{key}",
        )
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=inline("cancel", lang), callback_data="cancel")]]
    )


def music_models_keyboard(current_model: str, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, model in get_available_music_models().items():
        mark = "✅ " if key == current_model else ""
        cost = format_cost(model.cost_per_track, lang)
        builder.button(
            text=f"{mark}{model.name} ({cost})",
            callback_data=f"musicmodel:{key}",
        )
    builder.adjust(1)
    return builder.as_markup()


def cancel_music_keyboard(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=inline("cancel_music", lang), callback_data="cancel_music")]]
    )


def _buy_stars_button(lang: str = DEFAULT_LANG) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=inline("buy_stars", lang, price=SUBSCRIPTION_PRICE_STARS),
        url=STARS_TOPUP_URL,
    )


def _subscribe_button(lang: str = DEFAULT_LANG) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=inline("subscribe", lang, price=SUBSCRIPTION_PRICE_STARS),
        callback_data="subscribe",
    )


def referral_keyboard(bot_username: str, user_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    from bot.utils.growth import share_url

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=inline("share_bot", lang), url=share_url(bot_username, user_id, lang))],
            [_buy_stars_button(lang)],
            [_subscribe_button(lang)],
        ]
    )


def growth_keyboard(bot_username: str, user_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    from bot.utils.growth import share_url

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=inline("share_bot_bonus", lang), url=share_url(bot_username, user_id, lang))],
            [_buy_stars_button(lang)],
            [_subscribe_button(lang)],
        ]
    )


def image_share_keyboard(bot_username: str, user_id: int, lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    from bot.utils.growth import image_share_url

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=inline("share_this_bot", lang), url=image_share_url(bot_username, user_id, lang))],
        ]
    )


def subscription_keyboard(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_buy_stars_button(lang)],
            [_subscribe_button(lang)],
        ]
    )


def daily_reminder_keyboard(lang: str = DEFAULT_LANG) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=inline("claim_daily", lang), callback_data="claim_daily")],
        ]
    )
