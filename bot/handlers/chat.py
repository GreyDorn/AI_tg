import asyncio
import html
import logging
from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import MODELS, MAX_CONTEXT_MESSAGES, VISION_MODEL_KEY, DEFAULT_VISION_PROMPT, GEMINI_API_KEY
from db.models import User
from db.repository import (
    get_active_conversation,
    create_conversation,
    add_message,
    get_conversation_messages,
    spend_credits,
    add_credits,
)
from llm import get_llm
from llm.gemini import GeminiLLM, VISION_UNAVAILABLE_MSG
from bot.keyboards.main import models_keyboard
from bot.utils.formatting import format_model_text

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


def _vision_model_cfg():
    return MODELS[VISION_MODEL_KEY]


async def _download_photo_bytes(message: Message) -> tuple[bytes, str]:
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    downloaded = await message.bot.download_file(file.file_path)
    if hasattr(downloaded, "read"):
        data = downloaded.read()
    else:
        data = bytes(downloaded)
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("Image is too large. Maximum size is 4 MB.")
    return data, "image/jpeg"


def _photo_user_content(caption: str | None) -> str:
    caption = (caption or "").strip()
    return f"[📷 Image] {caption}" if caption else "[📷 Image]"


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
            await reply.edit_text("⚠️ The model returned an empty response.")
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

        if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower() or "resource_exhausted" in error_str.lower():
            await reply.edit_text(
                f"⏳ <b>Model is overloaded</b>\n\n"
                f"<b>{model_name}</b> has reached its request limit.\n\n"
                f"Choose another model 👇",
                parse_mode="HTML",
                reply_markup=models_keyboard(model_key),
            )
        elif "402" in error_str or "insufficient balance" in error_str.lower() or "payment required" in error_str.lower():
            await reply.edit_text(
                f"💳 <b>Model temporarily unavailable</b>\n\n"
                f"<b>{model_name}</b> is not available right now due to provider limits.\n\n"
                f"Choose another model 👇",
                parse_mode="HTML",
                reply_markup=models_keyboard(model_key),
            )
        elif "decommissioned" in error_str or "not supported" in error_str:
            await reply.edit_text(
                f"❌ <b>Model unavailable</b>\n\n"
                f"<b>{model_name}</b> was decommissioned by the provider.\n\n"
                f"Choose another model 👇",
                parse_mode="HTML",
                reply_markup=models_keyboard(model_key),
            )
        elif "too large" in error_str.lower() or "entity too large" in error_str.lower() or "context" in error_str.lower():
            await reply.edit_text(
                f"📝 <b>Conversation context is too large</b>\n\n"
                f"Start a new chat with /newchat or tap <b>💬 New Chat</b> — "
                f"this will clear the history so you can continue.",
                parse_mode="HTML",
            )
        elif VISION_UNAVAILABLE_MSG in error_str or "gemini api" in error_str.lower():
            await reply.edit_text(
                "📷 <b>Photo analysis is not available</b>\n\n"
                "Gemini API is not configured on this bot.",
                parse_mode="HTML",
            )
        else:
            await reply.edit_text(
                f"⚠️ <b>Model error</b>\n\n"
                f"Try again or choose a different model 👇",
                parse_mode="HTML",
                reply_markup=models_keyboard(model_key),
            )
        return

    await add_message(db_session, conv_id, "assistant", full_response)


async def _ensure_credits(message: Message, db_user: User, cost: int) -> bool:
    if db_user.has_unlimited_access or db_user.credits >= cost:
        return True
    await message.answer(
        f"❌ <b>Out of requests</b>\n\n"
        f"You have: <b>{db_user.credits}</b>\n\n"
        f"Come back tomorrow for free requests 🎁\n"
        f"Or get unlimited access → /buy",
        parse_mode="HTML",
    )
    return False


@router.message(F.text & ~F.text.startswith("/") & ~F.text.in_({"💬 New Chat", "🤖 Models", "💰 Balance", "👥 Referral", "💎 Subscription", "🎨 Create Image", "🖼 Image Models", "🎵 Create Music", "🎵 Music Models"}))
async def handle_message(message: Message, db_session: AsyncSession, db_user: User) -> None:
    if db_user.waiting_for_image or db_user.waiting_for_music:
        return

    model_key = db_user.current_model
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
            await message.answer(
                f"❌ <b>Out of requests</b>\n\n"
                f"You have: <b>{db_user.credits}</b>\n\n"
                f"Come back tomorrow for free requests 🎁\n"
                f"Or get unlimited access → /buy",
                parse_mode="HTML",
            )
            return

    await message.bot.send_chat_action(message.chat.id, "typing")
    reply = await message.answer("⏳")
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
    )


@router.message(F.photo)
async def handle_photo(message: Message, db_session: AsyncSession, db_user: User) -> None:
    if db_user.waiting_for_image:
        await message.answer(
            "🎨 You are in <b>image drawing</b> mode.\n\n"
            "Send a <b>text description</b>, or tap ❌ Cancel to exit.",
            parse_mode="HTML",
        )
        return
    if db_user.waiting_for_music:
        return

    if not GEMINI_API_KEY:
        await message.answer(
            "📷 <b>Photo analysis is not available</b>\n\n"
            "Gemini API is not configured on this bot.",
            parse_mode="HTML",
        )
        return

    vision_cfg = _vision_model_cfg()
    if not await _ensure_credits(message, db_user, vision_cfg.cost_per_message):
        return

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
            await message.answer(
                f"❌ <b>Out of requests</b>\n\n"
                f"You have: <b>{db_user.credits}</b>\n\n"
                f"Come back tomorrow for free requests 🎁\n"
                f"Or get unlimited access → /buy",
                parse_mode="HTML",
            )
            return

    try:
        image_bytes, mime_type = await _download_photo_bytes(message)
    except ValueError as exc:
        await message.answer(f"❌ {exc}")
        return
    except Exception:
        logger.exception("Failed to download photo user=%s", db_user.id)
        await message.answer("⚠️ Could not download the image. Please try again.")
        return

    prompt = (message.caption or "").strip() or DEFAULT_VISION_PROMPT
    logger.info("Photo analysis user=%s prompt=%r size=%d", db_user.id, prompt[:120], len(image_bytes))

    await message.bot.send_chat_action(message.chat.id, "typing")
    reply = await message.answer("📷 Analyzing with Gemini...")

    await _reply_streaming(
        message,
        reply,
        db_session,
        db_user,
        conv.id,
        VISION_MODEL_KEY,
        vision_cfg.name,
        credits_spent,
        _vision_llm.stream_vision(
            image_bytes,
            mime_type,
            prompt,
            context,
            vision_cfg.id,
        ),
    )
