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
from bot.i18n import all_menu_button_texts, button_filter, format_cost, resolve_lang, t

router = Router()
logger = logging.getLogger(__name__)

MENU_BUTTONS = all_menu_button_texts()


class WaitingForMusicFilter(BaseFilter):
    async def __call__(self, message: Message, db_user: User) -> bool:
        return db_user.waiting_for_music


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


async def _music_disabled_message(message: Message, lang: str) -> None:
    await message.answer(t("music_disabled", lang), parse_mode="HTML")


async def _music_unavailable_message(message: Message, lang: str) -> None:
    await message.answer(t("music_unavailable", lang), parse_mode="HTML")


async def _show_music_help(message: Message, db_user: User, waiting: bool = False, lang: str = "en") -> None:
    model_key, model_cfg = _get_music_model(db_user)
    cost = format_cost(model_cfg.cost_per_track, lang)

    if waiting:
        text = t("music_help_waiting", lang, model=model_cfg.name, cost=cost, duration=model_cfg.duration_seconds)
    else:
        text = t("music_help", lang, model=model_cfg.name, cost=cost, duration=model_cfg.duration_seconds)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=cancel_music_keyboard(lang) if waiting else music_models_keyboard(model_key, lang),
    )


async def _generate_and_send(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    prompt: str,
) -> None:
    lang = resolve_lang(db_user)
    if not is_pollinations_music_configured():
        await _music_unavailable_message(message, lang)
        return

    model_key, model_cfg = _get_music_model(db_user)
    if model_key != db_user.current_music_model:
        db_user.current_music_model = model_key
        await update_user_music_model(db_session, db_user.id, model_key)
    cost = model_cfg.cost_per_track

    if len(prompt) > 1000:
        await message.answer(t("image_prompt_too_long", lang))
        return

    if cost > 0 and db_user.credits < cost and not db_user.has_unlimited_access:
        await message.answer(
            t(
                "music_not_enough",
                lang,
                model=model_cfg.name,
                cost=cost,
                credits=db_user.credits,
            ),
            parse_mode="HTML",
            reply_markup=music_models_keyboard(model_key, lang),
        )
        return

    status = await message.answer(
        t("music_composing", lang, model=model_cfg.name),
        parse_mode="HTML",
    )
    await message.bot.send_chat_action(message.chat.id, "upload_voice")

    try:
        audio_bytes, _mime_type, ext = await generate_music(prompt, model_key)
    except MusicGenerationError as exc:
        logger.error("Music generation failed user=%s model=%s: %s", db_user.id, model_key, exc)
        error_text = str(exc)
        if "401" in error_text or "invalid" in error_text.lower():
            user_message = t("music_api_invalid", lang)
        elif "402" in error_text or "insufficient" in error_text.lower() or "credits" in error_text.lower():
            user_message = t("music_credits_depleted", lang)
        elif "429" in error_text or "rate" in error_text.lower():
            user_message = t("image_busy", lang)
        else:
            user_message = t("music_failed", lang)
        await status.edit_text(user_message, parse_mode="HTML", reply_markup=music_models_keyboard(model_key, lang))
        return
    except Exception:
        logger.exception("Unexpected music generation error user=%s model=%s", db_user.id, model_key)
        await status.edit_text(t("music_failed_later", lang))
        return

    if cost > 0 and not db_user.has_unlimited_access:
        spent = await spend_credits(db_session, db_user.id, cost)
        if not spent:
            await status.edit_text(t("image_spend_failed", lang))
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
        await message.answer(t("music_send_failed", lang))


@router.callback_query(F.data == "cancel_music")
async def cancel_music_prompt(
    callback: CallbackQuery,
    db_session: AsyncSession,
    db_user: User,
    lang: str = "en",
) -> None:
    if not db_user.waiting_for_music:
        await callback.answer(t("music_cancel_nothing", lang))
        return
    await _set_waiting(db_session, db_user, False)
    await callback.message.edit_text(t("music_cancelled", lang))
    await callback.answer()


@router.message(Command("music"))
async def cmd_music(
    message: Message,
    command: CommandObject,
    db_session: AsyncSession,
    db_user: User,
    lang: str = "en",
) -> None:
    if not is_music_feature_enabled():
        await _music_disabled_message(message, lang)
        return
    if not is_pollinations_music_configured():
        await _music_unavailable_message(message, lang)
        return

    prompt = (command.args or "").strip()
    if not prompt:
        await _set_waiting(db_session, db_user, True)
        await _show_music_help(message, db_user, waiting=True, lang=lang)
        return
    await _set_waiting(db_session, db_user, False)
    await _generate_and_send(message, db_session, db_user, prompt)


@router.message(button_filter("create_music"))
async def btn_music(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    lang: str = "en",
) -> None:
    if not is_music_feature_enabled():
        await _music_disabled_message(message, lang)
        return
    if not is_pollinations_music_configured():
        await _music_unavailable_message(message, lang)
        return
    await _set_waiting(db_session, db_user, True)
    await _show_music_help(message, db_user, waiting=True, lang=lang)


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
