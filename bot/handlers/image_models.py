from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from config import IMAGE_MODELS, DEFAULT_IMAGE_MODEL
from db.models import User
from db.repository import update_user_image_model
from bot.keyboards.main import image_models_keyboard
from llm.provider_status import get_available_image_models, resolve_image_model_key

router = Router()


def _format_cost(cost: int) -> str:
    if cost == 0:
        return "free"
    if cost == 1:
        return "1 request"
    return f"{cost} requests"


async def _show_image_models(target: Message | CallbackQuery, db_user: User, db_session: AsyncSession) -> None:
    model_key = resolve_image_model_key(db_user.current_image_model)
    if model_key != db_user.current_image_model:
        db_user.current_image_model = model_key
        await update_user_image_model(db_session, db_user.id, model_key)

    available = get_available_image_models()
    current = available[model_key]
    hidden_note = ""
    if len(available) < len(IMAGE_MODELS):
        hidden_note = "\n\n<i>Premium image models are hidden until OpenRouter credits are available.</i>"

    text = (
        f"🖼 <b>Image Models</b>\n\n"
        f"Current: <b>{current.name}</b> ({_format_cost(current.cost_per_image)})\n\n"
        f"Pick a model, then send /image or tap 🎨 Create Image."
        f"{hidden_note}"
    )
    markup = image_models_keyboard(model_key)

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
    available = get_available_image_models()

    if model_key not in available:
        await callback.answer("This model is currently unavailable.", show_alert=True)
        return

    if model_key == db_user.current_image_model:
        try:
            await callback.answer("This model is already selected ✅")
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
