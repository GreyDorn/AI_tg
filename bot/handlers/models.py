from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from config import MODELS, resolve_model_key
from db.models import User
from db.repository import update_user_model, create_conversation, clear_waiting_modes
from bot.keyboards.main import models_keyboard

router = Router()


async def _show_models(target: Message | CallbackQuery, db_user: User, db_session: AsyncSession) -> None:
    await clear_waiting_modes(db_session, db_user.id)
    db_user.waiting_for_image = False
    db_user.waiting_for_music = False

    resolved = resolve_model_key(db_user.current_model)
    if resolved != db_user.current_model:
        db_user.current_model = resolved
        await update_user_model(db_session, db_user.id, resolved)

    text = (
        f"🤖 <b>Choose a Model</b>\n\n"
        f"Current: <b>{MODELS[db_user.current_model].name}</b>\n\n"
        f"1 request per message for all models.\n"
        f"📷 — can read photos in chat (Gemini)"
    )
    markup = models_keyboard(db_user.current_model)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(Command("models"))
@router.message(F.text == "🤖 Models")
async def cmd_models(message: Message, db_session: AsyncSession, db_user: User) -> None:
    await _show_models(message, db_user, db_session)


@router.callback_query(F.data.startswith("model:"))
async def select_model(callback: CallbackQuery, db_session: AsyncSession, db_user: User) -> None:
    model_key = callback.data.split(":", 1)[1]

    if model_key not in MODELS:
        await callback.answer("Unknown model.", show_alert=True)
        return

    current_key = resolve_model_key(db_user.current_model)
    if model_key == current_key:
        try:
            await callback.answer("This model is already selected ✅")
        except Exception:
            pass
        await _show_models(callback, db_user, db_session)
        return

    await update_user_model(db_session, db_user.id, model_key)
    db_user.current_model = model_key
    await create_conversation(db_session, db_user.id, model_key)

    try:
        await callback.answer(f"✅ Switched to {MODELS[model_key].name}")
    except Exception:
        pass
    await _show_models(callback, db_user, db_session)
