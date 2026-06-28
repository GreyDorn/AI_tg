from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from config import MUSIC_MODELS
from db.models import User
from db.repository import update_user_music_model
from bot.keyboards.main import music_models_keyboard
from bot.i18n import button_filter, btn, format_cost, t
from llm.music_gen import is_pollinations_music_configured, is_music_feature_enabled
from llm.provider_status import get_available_music_models, resolve_music_model_key

router = Router()


async def _show_music_models(
    target: Message | CallbackQuery,
    db_user: User,
    db_session: AsyncSession,
    lang: str = "en",
) -> None:
    if not is_pollinations_music_configured():
        text = t("music_models_not_configured", lang)
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
    text = t(
        "music_models_title",
        lang,
        model=current.name,
        cost=format_cost(current.cost_per_track, lang),
        duration=current.duration_seconds,
        create_btn=btn("create_music", lang),
    )
    markup = music_models_keyboard(model_key, lang)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(Command("musicmodels"))
@router.message(button_filter("music_models"))
async def cmd_music_models(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    lang: str = "en",
) -> None:
    if not is_music_feature_enabled():
        await message.answer(t("music_disabled", lang), parse_mode="HTML")
        return
    await _show_music_models(message, db_user, db_session, lang)


@router.callback_query(F.data.startswith("musicmodel:"))
async def select_music_model(
    callback: CallbackQuery,
    db_session: AsyncSession,
    db_user: User,
    lang: str = "en",
) -> None:
    if not is_pollinations_music_configured():
        await callback.answer(t("music_not_configured_alert", lang), show_alert=True)
        return

    model_key = callback.data.split(":", 1)[1]
    available = get_available_music_models()

    if model_key not in available:
        await callback.answer(t("image_model_unavailable_alert", lang), show_alert=True)
        return

    if model_key == db_user.current_music_model:
        try:
            await callback.answer(t("model_already", lang))
        except Exception:
            pass
        return

    await update_user_music_model(db_session, db_user.id, model_key)
    db_user.current_music_model = model_key

    try:
        await callback.answer(t("image_model_selected", lang, model=MUSIC_MODELS[model_key].name))
    except Exception:
        pass
    await _show_music_models(callback, db_user, db_session, lang)
