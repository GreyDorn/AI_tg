from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from config import IMAGE_MODELS
from db.models import User
from db.repository import update_user_image_model, set_waiting_for_image
from bot.keyboards.main import image_models_keyboard, cancel_keyboard
from bot.i18n import button_filter, format_cost, resolve_lang
from llm.provider_status import get_available_image_models, resolve_image_model_key

router = Router()


def _format_cost(cost: int, lang: str) -> str:
    return format_cost(cost, lang)


async def _enable_image_waiting(db_session: AsyncSession, db_user: User) -> None:
    if not db_user.waiting_for_image:
        await set_waiting_for_image(db_session, db_user.id, True)
        db_user.waiting_for_image = True


async def _send_image_waiting_hint(target: Message, model_name: str, lang: str = "en") -> None:
    await target.answer(
        f"🎨 <b>Ready to draw</b> — model: <b>{model_name}</b>\n\n"
        f"Describe your image in the <b>next message</b>.\n"
        f"Example: <code>astronaut cat on the Moon</code>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(lang),
    )


async def _show_image_models(
    target: Message | CallbackQuery,
    db_user: User,
    db_session: AsyncSession,
    *,
    enable_waiting: bool = False,
    lang: str = "en",
) -> str:
    model_key = resolve_image_model_key(db_user.current_image_model)
    if model_key != db_user.current_image_model:
        db_user.current_image_model = model_key
        await update_user_image_model(db_session, db_user.id, model_key)

    if enable_waiting:
        await _enable_image_waiting(db_session, db_user)

    available = get_available_image_models()
    current = available[model_key]
    hidden_note = ""
    if len(available) < len(IMAGE_MODELS):
        hidden_note = "\n\n<i>Premium image models are hidden until OpenRouter credits are available.</i>"

    text = (
        f"🖼 <b>Image Models</b>\n\n"
        f"Current: <b>{current.name}</b> ({_format_cost(current.cost_per_image, lang)})\n\n"
        f"Pick a model or just describe your image in the <b>next message</b> 👇"
        f"{hidden_note}"
    )
    markup = image_models_keyboard(model_key, lang)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=markup)
    return current.name


@router.message(Command("imagemodels"))
@router.message(button_filter("image_models"))
async def cmd_image_models(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    lang: str = "en",
) -> None:
    model_name = await _show_image_models(message, db_user, db_session, enable_waiting=True, lang=lang)
    await _send_image_waiting_hint(message, model_name, lang)


@router.callback_query(F.data.startswith("imagemodel:"))
async def select_image_model(
    callback: CallbackQuery,
    db_session: AsyncSession,
    db_user: User,
    lang: str = "en",
) -> None:
    model_key = callback.data.split(":", 1)[1]
    available = get_available_image_models()

    if model_key not in available:
        await callback.answer("This model is currently unavailable.", show_alert=True)
        return

    already_selected = model_key == db_user.current_image_model

    if not already_selected:
        await update_user_image_model(db_session, db_user.id, model_key)
        db_user.current_image_model = model_key

    model_name = await _show_image_models(
        callback, db_user, db_session, enable_waiting=True, lang=lang,
    )

    try:
        if already_selected:
            await callback.answer(f"✅ {IMAGE_MODELS[model_key].name} — describe your image")
        else:
            await callback.answer(f"✅ {IMAGE_MODELS[model_key].name}")
    except Exception:
        pass

    await _send_image_waiting_hint(callback.message, model_name, lang)
