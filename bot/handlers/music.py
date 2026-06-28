import logging
from aiogram import Router, F
from aiogram.filters import Command, CommandObject, BaseFilter
from aiogram.types import Message, BufferedInputFile, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from config import MUSIC_MODELS
from db.models import User
from db.repository import spend_credits, update_user_music_model, set_waiting_for_music
from llm.music_gen import generate_music, MusicGenerationError, is_pollinations_music_configured, is_music_feature_enabled
from llm.provider_status import resolve_music_model_key
from bot.keyboards.main import music_models_keyboard, cancel_music_keyboard
from bot.i18n import all_menu_button_texts, button_filter

router = Router()
logger = logging.getLogger(__name__)

MENU_BUTTONS = all_menu_button_texts()


class WaitingForMusicFilter(BaseFilter):
    async def __call__(self, message: Message, db_user: User) -> bool:
        return db_user.waiting_for_music


def _format_cost(cost: int) -> str:
    if cost == 0:
        return "free"
    if cost == 1:
        return "1 request"
    return f"{cost} requests"


def _get_music_model(db_user: User) -> tuple[str, object]:
    model_key = resolve_music_model_key(db_user.current_music_model)
    return model_key, MUSIC_MODELS[model_key]


async def _set_waiting(
    db_session: AsyncSession,
    db_user: User,
    waiting: bool,
) -> None:
    if db_user.waiting_for_music == waiting:
        return
    await set_waiting_for_music(db_session, db_user.id, waiting)
    db_user.waiting_for_music = waiting


async def _music_disabled_message(message: Message) -> None:
    await message.answer(
        "🎵 <b>Music generation is temporarily unavailable</b>\n\n"
        "This feature will return when a free music API is available.",
        parse_mode="HTML",
    )


async def _music_unavailable_message(message: Message) -> None:
    await message.answer(
        "🎵 <b>Music generation is not available</b>\n\n"
        "Pollinations API key is missing. Ask the bot admin to add "
        "<code>POLLINATIONS_API_KEY</code> to <code>.env</code>.\n"
        "Get a key: https://enter.pollinations.ai",
        parse_mode="HTML",
    )


async def _show_music_help(message: Message, db_user: User, waiting: bool = False) -> None:
    model_key, model_cfg = _get_music_model(db_user)
    cost = _format_cost(model_cfg.cost_per_track)

    if waiting:
        text = (
            f"🎵 <b>Describe your music in one message</b>\n\n"
            f"Model: <b>{model_cfg.name}</b> ({cost}, ~{model_cfg.duration_seconds}s)\n"
            f"Example: <code>upbeat electronic dance track with synths</code>\n\n"
            f"Change model → /musicmodels"
        )
    else:
        text = (
            f"🎵 <b>Music Generation</b>\n\n"
            f"Model: <b>{model_cfg.name}</b> ({cost}, ~{model_cfg.duration_seconds}s)\n\n"
            f"Send a command:\n"
            f"<code>/music upbeat electronic dance track</code>\n\n"
            f"Change model → /musicmodels"
        )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=cancel_music_keyboard() if waiting else music_models_keyboard(model_key),
    )


async def _generate_and_send(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    prompt: str,
) -> None:
    if not is_pollinations_music_configured():
        await _music_unavailable_message(message)
        return

    model_key, model_cfg = _get_music_model(db_user)
    if model_key != db_user.current_music_model:
        db_user.current_music_model = model_key
        await update_user_music_model(db_session, db_user.id, model_key)
    cost = model_cfg.cost_per_track

    if len(prompt) > 1000:
        await message.answer("❌ Description is too long. Maximum 1000 characters.")
        return

    if cost > 0 and db_user.credits < cost and not db_user.has_unlimited_access:
        await message.answer(
            f"❌ <b>Not enough requests</b>\n\n"
            f"<b>{model_cfg.name}</b> costs <b>{cost}</b> requests.\n"
            f"You have: <b>{db_user.credits}</b>\n\n"
            f"Try a free model → /musicmodels\n"
            f"Unlimited access → /buy",
            parse_mode="HTML",
            reply_markup=music_models_keyboard(model_key),
        )
        return

    status = await message.answer(
        f"🎵 Composing with <b>{model_cfg.name}</b>... Please wait 30–90 sec.",
        parse_mode="HTML",
    )
    await message.bot.send_chat_action(message.chat.id, "upload_voice")

    try:
        audio_bytes, _mime_type, ext = await generate_music(prompt, model_key)
    except MusicGenerationError as exc:
        logger.error("Music generation failed user=%s model=%s: %s", db_user.id, model_key, exc)
        error_text = str(exc)
        if "401" in error_text or "invalid" in error_text.lower():
            user_message = "🔑 Music API key is invalid. Contact the bot admin."
        elif "402" in error_text or "insufficient" in error_text.lower() or "credits" in error_text.lower():
            user_message = (
                "💳 <b>Music service credits depleted</b>\n\n"
                "Try again later or contact the bot admin."
            )
        elif "429" in error_text or "rate" in error_text.lower():
            user_message = "⏳ Service is busy. Please try again in a minute."
        else:
            user_message = "⚠️ Could not create the music. Try another model → /musicmodels"
        await status.edit_text(user_message, parse_mode="HTML", reply_markup=music_models_keyboard(model_key))
        return
    except Exception:
        logger.exception("Unexpected music generation error user=%s model=%s", db_user.id, model_key)
        await status.edit_text("⚠️ Could not create the music. Please try again later.")
        return

    if cost > 0 and not db_user.has_unlimited_access:
        spent = await spend_credits(db_session, db_user.id, cost)
        if not spent:
            await status.edit_text("❌ Not enough requests to complete this action.")
            return

    title = prompt[:64] if len(prompt) > 64 else prompt
    caption = f"🎵 {model_cfg.name}\n{prompt[:850]}"

    try:
        await status.delete()
    except Exception:
        pass

    try:
        await message.answer_audio(
            BufferedInputFile(audio_bytes, filename=f"music.{ext}"),
            title=title,
            caption=caption,
        )
    except Exception:
        logger.exception("Failed to send audio user=%s model=%s", db_user.id, model_key)
        await message.answer(
            "⚠️ Music was generated but could not be sent. Please try again.",
        )


@router.callback_query(F.data == "cancel_music")
async def cancel_music_prompt(
    callback: CallbackQuery,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    if not db_user.waiting_for_music:
        await callback.answer("Nothing to cancel.")
        return
    await _set_waiting(db_session, db_user, False)
    await callback.message.edit_text("❌ Music generation cancelled.")
    await callback.answer()


@router.message(Command("music"))
async def cmd_music(
    message: Message,
    command: CommandObject,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    if not is_music_feature_enabled():
        await _music_disabled_message(message)
        return
    if not is_pollinations_music_configured():
        await _music_unavailable_message(message)
        return

    prompt = (command.args or "").strip()
    if not prompt:
        await _set_waiting(db_session, db_user, True)
        await _show_music_help(message, db_user, waiting=True)
        return
    await _set_waiting(db_session, db_user, False)
    await _generate_and_send(message, db_session, db_user, prompt)


@router.message(button_filter("create_music"))
async def btn_music(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    if not is_music_feature_enabled():
        await _music_disabled_message(message)
        return
    if not is_pollinations_music_configured():
        await _music_unavailable_message(message)
        return
    await _set_waiting(db_session, db_user, True)
    await _show_music_help(message, db_user, waiting=True)


@router.message(F.text, WaitingForMusicFilter())
async def music_prompt_followup(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    if not message.text or message.text.startswith("/") or message.text in MENU_BUTTONS:
        await _set_waiting(db_session, db_user, False)
        return

    await _set_waiting(db_session, db_user, False)
    await _generate_and_send(message, db_session, db_user, message.text.strip())
