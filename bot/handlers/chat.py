import asyncio
import html
import logging
from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import MODELS, MAX_CONTEXT_MESSAGES, DEFAULT_VISION_MODEL_KEY, DEFAULT_VISION_PROMPT, GEMINI_API_KEY, resolve_model_key
from db.models import User
from db.repository import (
    get_active_conversation,
    create_conversation,
    add_message,
    get_conversation_messages,
    spend_credits,
    add_credits,
    update_user_model,
    clear_waiting_modes,
)
from llm import get_llm
from llm.gemini import GeminiLLM, VISION_UNAVAILABLE_MSG
from bot.keyboards.main import models_keyboard
from bot.utils.formatting import format_model_text
from bot.i18n import all_menu_button_texts, resolve_lang, t, btn
from bot.utils.growth import answer_out_of_credits, answer_low_credits_hint

router = Router()
logger = logging.getLogger(__name__)
_vision_llm = GeminiLLM()

STREAM_EDIT_INTERVAL = 0.8
TG_MAX_LENGTH = 4096


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


def _vision_model_for_user(db_user: User) -> tuple[str, object]:
    current_key = resolve_model_key(db_user.current_model)
    current_cfg = MODELS[current_key]
    if current_cfg.supports_vision and current_cfg.provider == "google":
        return current_key, current_cfg
    default_cfg = MODELS[DEFAULT_VISION_MODEL_KEY]
    return DEFAULT_VISION_MODEL_KEY, default_cfg


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


def _photo_user_content(caption: str | None) -> str:
    caption = (caption or "").strip()
    return f"[📷 Image] {caption}" if caption else "[📷 Image]"


VISION_ERROR_KEY = "chat_vision_failed"


async def _revert_auto_switched_model(
    db_session: AsyncSession,
    db_user: User,
    previous_model_key: str | None,
) -> None:
    if not previous_model_key or db_user.current_model == previous_model_key:
        return
    await update_user_model(db_session, db_user.id, previous_model_key)
    db_user.current_model = previous_model_key


async def _reply_photo_failed(
    reply: Message,
    db_session: AsyncSession,
    db_user: User,
    *,
    previous_model_key: str | None = None,
    lang: str = "en",
) -> None:
    await _revert_auto_switched_model(db_session, db_user, previous_model_key)
    await reply.edit_text(t(VISION_ERROR_KEY, lang), parse_mode="HTML")


def _is_rate_limited(error_str: str) -> bool:
    low = error_str.lower()
    return (
        "429" in error_str
        or "quota" in low
        or "rate" in low
        or "resource_exhausted" in low
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
            if credits_spent:
                await add_credits(db_session, db_user.id, credits_spent)
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
        if credits_spent:
            await add_credits(db_session, db_user.id, credits_spent)
        error_str = str(e)
        logger.error("LLM error for user %s model %s: %s", db_user.id, model_key, error_str)

        if vision_mode:
            if VISION_UNAVAILABLE_MSG in error_str or "gemini api" in error_str.lower():
                await reply.edit_text(t("chat_vision_unavailable", lang), parse_mode="HTML")
            else:
                await _reply_photo_failed(
                    reply, db_session, db_user, previous_model_key=revert_model_key, lang=lang,
                )
        elif _is_rate_limited(error_str):
            await reply.edit_text(
                t("chat_rate_limited", lang, model=model_name),
                parse_mode="HTML",
                reply_markup=models_keyboard(model_key),
            )
        elif "402" in error_str or "insufficient balance" in error_str.lower() or "payment required" in error_str.lower():
            await reply.edit_text(
                t("chat_provider_limit", lang, model=model_name),
                parse_mode="HTML",
                reply_markup=models_keyboard(model_key),
            )
        elif "decommissioned" in error_str or "not supported" in error_str:
            await reply.edit_text(
                t("chat_model_gone", lang, model=model_name),
                parse_mode="HTML",
                reply_markup=models_keyboard(model_key),
            )
        elif "too large" in error_str.lower() or "entity too large" in error_str.lower() or "context" in error_str.lower():
            await reply.edit_text(
                t("chat_context_large", lang, new_chat_btn=btn("new_chat", lang)),
                parse_mode="HTML",
            )
        else:
            await reply.edit_text(
                t("chat_model_error", lang),
                parse_mode="HTML",
                reply_markup=models_keyboard(model_key),
            )
        return

    await add_message(db_session, conv_id, "assistant", full_response)

    if not vision_mode and not db_user.has_unlimited_access:
        await db_session.refresh(db_user)
        if db_user.credits in (1, 2):
            await answer_low_credits_hint(message, db_user, db_user.credits, resolve_lang(db_user))


async def _ensure_credits(message: Message, db_user: User, cost: int) -> bool:
    if db_user.has_unlimited_access or db_user.credits >= cost:
        return True
    lang = resolve_lang(db_user)
    await answer_out_of_credits(message, db_user, lang)
    return False


@router.message(F.text & ~F.text.startswith("/") & ~F.text.in_(all_menu_button_texts()))
async def handle_message(message: Message, db_session: AsyncSession, db_user: User, lang: str = "en") -> None:
    if db_user.waiting_for_image or db_user.waiting_for_music:
        return

    model_key = resolve_model_key(db_user.current_model)
    if model_key != db_user.current_model:
        await update_user_model(db_session, db_user.id, model_key)
        db_user.current_model = model_key
    model_cfg = MODELS[model_key]

    if not await _ensure_credits(message, db_user, model_cfg.cost_per_message):
        return

    conv = await get_active_conversation(db_session, db_user.id)
    if not conv:
        conv = await create_conversation(db_session, db_user.id, model_key)

    await add_message(db_session, conv.id, "user", message.text)

    all_messages = await get_conversation_messages(db_session, conv.id)
    context = all_messages[-MAX_CONTEXT_MESSAGES:]
    if len(all_messages) > len(context):
        logger.info(
            "Context window for user %s: using last %d of %d messages",
            db_user.id,
            len(context),
            len(all_messages),
        )

    credits_spent = 0
    if not db_user.has_unlimited_access:
        if await spend_credits(db_session, db_user.id, model_cfg.cost_per_message):
            credits_spent = model_cfg.cost_per_message
        else:
            await answer_out_of_credits(message, db_user, lang)
            return

    await message.bot.send_chat_action(message.chat.id, "typing")
    reply = await message.answer(t("chat_thinking", lang))
    llm, model_id, disable_thinking = get_llm(model_key)

    await _reply_streaming(
        message,
        reply,
        db_session,
        db_user,
        conv.id,
        model_key,
        model_cfg.name,
        credits_spent,
        llm.stream(context, model_id, disable_thinking),
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

    if not GEMINI_API_KEY:
        await message.answer(t("chat_vision_unavailable", lang), parse_mode="HTML")
        return

    vision_key, vision_cfg = _vision_model_for_user(db_user)
    if not await _ensure_credits(message, db_user, vision_cfg.cost_per_message):
        return

    previous_model_key = resolve_model_key(db_user.current_model)
    auto_switched = previous_model_key != vision_key
    revert_model_key = previous_model_key if auto_switched else None
    if auto_switched:
        await update_user_model(db_session, db_user.id, vision_key)
        db_user.current_model = vision_key

    conv = await get_active_conversation(db_session, db_user.id)
    if not conv:
        conv = await create_conversation(db_session, db_user.id, db_user.current_model)

    user_content = _photo_user_content(message.caption)
    await add_message(db_session, conv.id, "user", user_content)

    all_messages = await get_conversation_messages(db_session, conv.id)
    context = all_messages[:-1][-MAX_CONTEXT_MESSAGES:]

    credits_spent = 0
    if not db_user.has_unlimited_access:
        if await spend_credits(db_session, db_user.id, vision_cfg.cost_per_message):
            credits_spent = vision_cfg.cost_per_message
        else:
            await _revert_auto_switched_model(db_session, db_user, revert_model_key)
            await answer_out_of_credits(message, db_user, lang)
            return

    try:
        image_bytes, mime_type = await _download_photo_bytes(message)
    except ValueError:
        await _revert_auto_switched_model(db_session, db_user, revert_model_key)
        await message.answer(f"❌ {t('chat_image_too_large', lang)}")
        return
    except Exception:
        logger.exception("Failed to download photo user=%s", db_user.id)
        await _revert_auto_switched_model(db_session, db_user, revert_model_key)
        await message.answer(t("chat_image_download_failed", lang))
        return

    prompt = (message.caption or "").strip() or DEFAULT_VISION_PROMPT
    logger.info("Photo analysis user=%s prompt=%r size=%d", db_user.id, prompt[:120], len(image_bytes))

    await message.bot.send_chat_action(message.chat.id, "typing")
    if exited_image_mode and auto_switched:
        status = t("chat_photo_status_left_switched", lang, model=vision_cfg.name)
    elif exited_image_mode:
        status = t("chat_photo_status_left", lang, model=vision_cfg.name)
    elif auto_switched:
        status = t("chat_photo_status_switched", lang, model=vision_cfg.name)
    else:
        status = t("chat_photo_status", lang, model=vision_cfg.name)
    reply = await message.answer(status, parse_mode="HTML")

    await _reply_streaming(
        message,
        reply,
        db_session,
        db_user,
        conv.id,
        vision_key,
        vision_cfg.name,
        credits_spent,
        _vision_llm.stream_vision(
            image_bytes,
            mime_type,
            prompt,
            context,
            vision_cfg.id,
        ),
        vision_mode=True,
        revert_model_key=revert_model_key,
        lang=lang,
    )
