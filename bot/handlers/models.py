from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from config import MODELS
from db.models import User
from db.repository import update_user_model, create_conversation
from bot.keyboards.main import models_keyboard

router = Router()


async def _show_models(target: Message | CallbackQuery, db_user: User) -> None:
    text = (
        f"🤖 <b>Выбор модели</b>\n\n"
        f"Текущая: <b>{MODELS[db_user.current_model].name}</b>\n\n"
        f"Стоимость указана в 🔥 кредитах за сообщение."
    )
    markup = models_keyboard(db_user.current_model)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(Command("models"))
@router.message(F.text == "🤖 Модели")
async def cmd_models(message: Message, db_user: User) -> None:
    await _show_models(message, db_user)


@router.callback_query(F.data.startswith("model:"))
async def select_model(callback: CallbackQuery, db_session: AsyncSession, db_user: User) -> None:
    model_key = callback.data.split(":", 1)[1]

    if model_key not in MODELS:
        await callback.answer("Неизвестная модель.", show_alert=True)
        return

    if model_key == db_user.current_model:
        try:
            await callback.answer("Эта модель уже выбрана ✅")
        except Exception:
            pass
        return

    await update_user_model(db_session, db_user.id, model_key)
    db_user.current_model = model_key

    # Начинаем новый диалог с новой моделью
    await create_conversation(db_session, db_user.id, model_key)

    try:
        await callback.answer(f"✅ Модель изменена на {MODELS[model_key].name}")
    except Exception:
        pass  # Callback мог устареть при перезапуске бота
    await _show_models(callback, db_user)
