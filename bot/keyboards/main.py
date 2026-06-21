from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import MODELS, DEFAULT_MODEL, CREDIT_PACKAGES


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💬 Новый чат"), KeyboardButton(text="🤖 Модели")],
            [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="👥 Реферал")],
            [KeyboardButton(text="💳 Купить кредиты")],
        ],
        resize_keyboard=True,
    )


def models_keyboard(current_model: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, model in MODELS.items():
        mark = "✅ " if key == current_model else ""
        builder.button(
            text=f"{mark}{model.name} — {model.cost_per_message}🔥/msg",
            callback_data=f"model:{key}",
        )
    builder.adjust(1)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
    )


def referral_keyboard(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    ref_link = f"https://t.me/{bot_username}?start=ref{user_id}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}&text=Попробуй%20AI%20бот!")]
        ]
    )


def buy_packages_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for pack_id, (stars, credits, label) in CREDIT_PACKAGES.items():
        builder.button(text=label, callback_data=f"buy:{pack_id}")
    builder.adjust(1)
    return builder.as_markup()
