import asyncio
import html
import logging
from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import MONETIZATION_ENABLED
from db.models import User
from db.repository import clear_waiting_modes
from core.chat import (
    setup_text_chat,
    build_text_stream,
    save_assistant_message,
    setup_vision_chat,
    build_vision_stream,
    revert_user_model,
    is_vision_available,
)
from core.credits import refund
from core.errors import classify_llm_error, LlmErrorKind
from bot.keyboards.main import models_keyboard
from bot.utils.formatting import format_model_text
from bot.i18n import all_menu_button_texts, resolve_lang, t, btn
from bot.utils.growth import answer_out_of_credits, answer_low_credits_hint

router = Router()
logger = logging.getLogger(__name__)

STREAM_EDIT_INTERVAL = 0.8
TG_MAX_LENGTH = 4096
VISION_ERROR_KEY = "chat_vision_failed"


def _split_text(text: str, limit: int = TG_MAX_LENGTH) -> list[str]:
    """Разбивает длинный текст на части, стараясь резать по переносам строк."""
    parts = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        parts.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        parts.append(text)
    return parts


async def _send_formatted(reply: Message, text: str) -> None:
    try:
        await reply.edit_text(format_model_text(text))
    except Exception:
        await reply.edit_text(html.escape(text))


async def _answer_formatted(message: Message, text: str) -> None:
    try:
        await message.answer(format_model_text(text))
    except Exception:
        await message.answer(html.escape(text))


async def _download_photo_bytes(message: Message) -> tuple[bytes, str]:
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    downloaded = await message.bot.download_file(file.file_path)
    if hasattr(downloaded, "read"):
        data = downloaded.read()
    else:
        data = bytes(downloaded)
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("IMAGE_TOO_LARGE")
    return data, "image/jpeg"


async def _reply_photo_failed(
    reply: Message,
    db_session: AsyncSession,
    db_user: User,
    *,
    previous_model_key: str | None = None,
    lang: str = "en",
) -> None:
    await revert_user_model(db_session, db_user, previous_model_key)
    await reply.edit_text(t(VISION_ERROR_KEY, lang), parse_mode="HTML")


async def _reply_llm_error(
    reply: Message,
    error_kind: LlmErrorKind,
    *,
    model_key: str,
    model_name: str,
    lang: str,
) -> None:
    if error_kind == LlmErrorKind.RATE_LIMITED:
        await reply.edit_text(
            t("chat_rate_limited", lang, model=model_name),
            parse_mode="HTML",
            reply_markup=models_keyboard(model_key),
        )
    elif error_kind == LlmErrorKind.PROVIDER_LIMIT:
        await reply.edit_text(
            t("chat_provider_limit", lang, model=model_name),
            parse_mode="HTML",
            reply_markup=models_keyboard(model_key),
        )
    elif error_kind == LlmErrorKind.MODEL_GONE:
        await reply.edit_text(
            t("chat_model_gone", lang, model=model_name),
            parse_mode="HTML",
            reply_markup=models_keyboard(model_key),
        )
    elif error_kind == LlmErrorKind.CONTEXT_TOO_LARGE:
        await reply.edit_text(
            t("chat_context_large", lang, new_chat_btn=btn("new_chat", lang)),
            parse_mode="HTML",
        )
    elif error_kind == LlmErrorKind.VISION_UNAVAILABLE:
        await reply.edit_text(t("chat_vision_unavailable", lang), parse_mode="HTML")
    elif error_kind == LlmErrorKind.VISION_FAILED:
        await reply.edit_text(t(VISION_ERROR_KEY, lang), parse_mode="HTML")
    else:
        await reply.edit_text(
            t("chat_model_error", lang),
            parse_mode="HTML",
            reply_markup=models_keyboard(model_key),
        )


async def _reply_streaming(
    message: Message,
    reply: Message,
    db_session: AsyncSession,
    db_user: User,
    conv_id: int,
    model_key: str,
    model_name: str,
    credits_spent: int,
    stream,
    *,
    vision_mode: bool = False,
    revert_model_key: str | None = None,
    lang: str = "en",
) -> None:
    full_response = ""
    last_edit_time = asyncio.get_event_loop().time()

    try:
        async for chunk in stream:
            full_response += chunk
            now = asyncio.get_event_loop().time()
            if now - last_edit_time >= STREAM_EDIT_INTERVAL:
                preview = full_response[-TG_MAX_LENGTH + 3:] if len(full_response) > TG_MAX_LENGTH else full_response
                try:
                    await reply.edit_text(html.escape(preview) + " ▌")
                    last_edit_time = now
                except Exception:
                    pass

        if not full_response:
            await refund(db_session, db_user.id, credits_spent)
            if vision_mode:
                await _reply_photo_failed(
                    reply, db_session, db_user, previous_model_key=revert_model_key, lang=lang,
                )
            else:
                await reply.edit_text(t("chat_empty_response", lang))
            return

        parts = _split_text(full_response)
        await _send_formatted(reply, parts[0])
        for part in parts[1:]:
            await _answer_formatted(message, part)

    except Exception as e:
        await refund(db_session, db_user.id, credits_spent)
        error_str = str(e)
        logger.error("LLM error for user %s model %s: %s", db_user.id, model_key, error_str)

        error_kind = classify_llm_error(e, vision_mode=vision_mode)
        if vision_mode and error_kind == LlmErrorKind.VISION_FAILED:
            await _reply_photo_failed(
                reply, db_session, db_user, previous_model_key=revert_model_key, lang=lang,
            )
        else:
            await _reply_llm_error(
                reply, error_kind, model_key=model_key, model_name=model_name, lang=lang,
            )
        return

    await save_assistant_message(db_session, conv_id, full_response)

    if MONETIZATION_ENABLED and not vision_mode and not db_user.has_unlimited_access:
        await db_session.refresh(db_user)
        if db_user.credits in (1, 2):
            await answer_low_credits_hint(message, db_user, db_user.credits, resolve_lang(db_user))


@router.message(F.text & ~F.text.startswith("/") & ~F.text.in_(all_menu_button_texts()))
async def handle_message(message: Message, db_session: AsyncSession, db_user: User, lang: str = "en") -> None:
    if db_user.waiting_for_image or db_user.waiting_for_music:
        return

    setup = await setup_text_chat(db_session, db_user, message.text)
    if setup is None:
        await answer_out_of_credits(message, db_user, lang)
        return

    await message.bot.send_chat_action(message.chat.id, "typing")
    reply = await message.answer(t("chat_thinking", lang))

    await _reply_streaming(
        message,
        reply,
        db_session,
        db_user,
        setup.conv_id,
        setup.model_key,
        setup.model_name,
        setup.credits_spent,
        build_text_stream(setup),
        lang=lang,
    )


@router.message(F.photo)
async def handle_photo(message: Message, db_session: AsyncSession, db_user: User, lang: str = "en") -> None:
    exited_image_mode = db_user.waiting_for_image
    if db_user.waiting_for_image:
        await clear_waiting_modes(db_session, db_user.id)
        db_user.waiting_for_image = False
        db_user.waiting_for_music = False
    if db_user.waiting_for_music:
        return

    if not is_vision_available():
        await message.answer(t("chat_vision_unavailable", lang), parse_mode="HTML")
        return

    try:
        image_bytes, mime_type = await _download_photo_bytes(message)
    except ValueError:
        await message.answer(f"❌ {t('chat_image_too_large', lang)}")
        return
    except Exception:
        logger.exception("Failed to download photo user=%s", db_user.id)
        await message.answer(t("chat_image_download_failed", lang))
        return

    setup = await setup_vision_chat(
        db_session,
        db_user,
        caption=message.caption,
        image_bytes=image_bytes,
        mime_type=mime_type,
    )
    if setup is None:
        await answer_out_of_credits(message, db_user, lang)
        return

    await message.bot.send_chat_action(message.chat.id, "typing")
    if exited_image_mode and setup.auto_switched:
        status = t("chat_photo_status_left_switched", lang, model=setup.vision_name)
    elif exited_image_mode:
        status = t("chat_photo_status_left", lang, model=setup.vision_name)
    elif setup.auto_switched:
        status = t("chat_photo_status_switched", lang, model=setup.vision_name)
    else:
        status = t("chat_photo_status", lang, model=setup.vision_name)
    reply = await message.answer(status, parse_mode="HTML")

    await _reply_streaming(
        message,
        reply,
        db_session,
        db_user,
        setup.conv_id,
        setup.vision_key,
        setup.vision_name,
        setup.credits_spent,
        build_vision_stream(setup),
        vision_mode=True,
        revert_model_key=setup.revert_model_key,
        lang=lang,
    )
