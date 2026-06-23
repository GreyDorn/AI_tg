from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from config import IMAGE_MODELS, DEFAULT_IMAGE_MODEL
from db.models import User
from db.repository import update_user_image_model
from bot.keyboards.main import image_models_keyboard

router = Router()


async def _show_image_models(target: Message | CallbackQuery, db_user: User, db_session: AsyncSession) -> None:
    if db_user.current_image_model not in IMAGE_MODELS:
        db_user.current_image_model = DEFAULT_IMAGE_MODEL
        await update_user_image_model(db_session, db_user.id, DEFAULT_IMAGE_MODEL)

    current = IMAGE_MODELS[db_user.current_image_model]
    cost = (
        "бесплатно"
        if current.cost_per_image == 0
        else f"{current.cost_per_image} запроса"
    )
    text = (
        f"🖼 <b>Модели для картинок</b>\n\n"
        f"Текущая: <b>{current.name}</b> ({cost})\n\n"
        f"Выберите модель, затем отправьте /image или нажмите 🎨 Create Image."
    )
    markup = image_models_keyboard(db_user.current_image_model)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(Command("imagemodels"))
@router.message(F.text == "🖼 Image Models")
async def cmd_image_models(message: Message, db_session: AsyncSession, db_user: User) -> None:
    await _show_image_models(message, db_user, db_session)


@router.callback_query(F.data.startswith("imagemodel:"))
async def select_image_model(callback: CallbackQuery, db_session: AsyncSession, db_user: User) -> None:
    model_key = callback.data.split(":", 1)[1]

    if model_key not in IMAGE_MODELS:
        await callback.answer("Неизвестная модель.", show_alert=True)
        return

    if model_key == db_user.current_image_model:
        try:
            await callback.answer("Эта модель уже выбрана ✅")
        except Exception:
            pass
        return

    await update_user_image_model(db_session, db_user.id, model_key)
    db_user.current_image_model = model_key

    try:
        await callback.answer(f"✅ {IMAGE_MODELS[model_key].name}")
    except Exception:
        pass
    await _show_image_models(callback, db_user, db_session)
