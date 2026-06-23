from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from config import MUSIC_MODELS
from db.models import User
from db.repository import update_user_music_model
from bot.keyboards.main import music_models_keyboard
from llm.music_gen import is_pollinations_music_configured, is_music_feature_enabled
from llm.provider_status import get_available_music_models, resolve_music_model_key

router = Router()


def _format_cost(cost: int) -> str:
    if cost == 0:
        return "free"
    if cost == 1:
        return "1 request"
    return f"{cost} requests"


async def _show_music_models(target: Message | CallbackQuery, db_user: User, db_session: AsyncSession) -> None:
    if not is_pollinations_music_configured():
        text = (
            "🎵 <b>Music generation is not configured</b>\n\n"
            "The bot needs a Pollinations API key.\n"
            "Get one at https://enter.pollinations.ai and add "
            "<code>POLLINATIONS_API_KEY</code> to <code>.env</code>."
        )
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, parse_mode="HTML")
        else:
            await target.answer(text, parse_mode="HTML")
        return

    model_key = resolve_music_model_key(db_user.current_music_model)
    if model_key != db_user.current_music_model:
        db_user.current_music_model = model_key
        await update_user_music_model(db_session, db_user.id, model_key)

    available = get_available_music_models()
    current = available[model_key]
    text = (
        f"🎵 <b>Music Models</b>\n\n"
        f"Current: <b>{current.name}</b> ({_format_cost(current.cost_per_track)}, "
        f"~{current.duration_seconds}s)\n\n"
        f"Pick a model, then send /music or tap 🎵 Create Music."
    )
    markup = music_models_keyboard(model_key)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(Command("musicmodels"))
@router.message(F.text == "🎵 Music Models")
async def cmd_music_models(message: Message, db_session: AsyncSession, db_user: User) -> None:
    if not is_music_feature_enabled():
        await message.answer(
            "🎵 <b>Music generation is temporarily unavailable</b>",
            parse_mode="HTML",
        )
        return
    await _show_music_models(message, db_user, db_session)


@router.callback_query(F.data.startswith("musicmodel:"))
async def select_music_model(callback: CallbackQuery, db_session: AsyncSession, db_user: User) -> None:
    if not is_pollinations_music_configured():
        await callback.answer("Music is not configured on this bot.", show_alert=True)
        return

    model_key = callback.data.split(":", 1)[1]
    available = get_available_music_models()

    if model_key not in available:
        await callback.answer("This model is currently unavailable.", show_alert=True)
        return

    if model_key == db_user.current_music_model:
        try:
            await callback.answer("This model is already selected ✅")
        except Exception:
            pass
        return

    await update_user_music_model(db_session, db_user.id, model_key)
    db_user.current_music_model = model_key

    try:
        await callback.answer(f"✅ {MUSIC_MODELS[model_key].name}")
    except Exception:
        pass
    await _show_music_models(callback, db_user, db_session)
