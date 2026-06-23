import asyncio
import html
import logging
from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import MODELS, MAX_CONTEXT_MESSAGES
from db.models import User
from db.repository import (
    get_active_conversation,
    create_conversation,
    add_message,
    get_conversation_messages,
    spend_credits,
)
from llm import get_llm
from bot.keyboards.main import models_keyboard
from bot.utils.formatting import format_model_text

router = Router()
logger = logging.getLogger(__name__)

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


@router.message(F.text & ~F.text.startswith("/") & ~F.text.in_({"💬 New Chat", "🤖 Models", "💰 Balance", "👥 Referral", "💎 Subscription", "🎨 Create Image", "🆓 Free Image"}))
async def handle_message(message: Message, db_session: AsyncSession, db_user: User) -> None:
    model_key = db_user.current_model
    model_cfg = MODELS[model_key]

    if db_user.credits < model_cfg.cost_per_message and not db_user.has_unlimited_access:
        await message.answer(
            f"❌ <b>Out of requests</b>\n\n"
            f"You have: <b>{db_user.credits}</b>\n\n"
            f"Come back tomorrow for free requests 🎁\n"
            f"Or get unlimited access → /buy",
            parse_mode="HTML",
        )
        return

    conv = await get_active_conversation(db_session, db_user.id)
    if not conv:
        conv = await create_conversation(db_session, db_user.id, model_key)

    await add_message(db_session, conv.id, "user", message.text)

    all_messages = await get_conversation_messages(db_session, conv.id)
    context = all_messages[-MAX_CONTEXT_MESSAGES:]

    await spend_credits(db_session, db_user.id, model_cfg.cost_per_message) if not db_user.has_unlimited_access else None
    await message.bot.send_chat_action(message.chat.id, "typing")

    reply = await message.answer("⏳")
    llm, model_id, disable_thinking = get_llm(model_key)

    full_response = ""
    last_edit_time = asyncio.get_event_loop().time()

    try:
        async for chunk in llm.stream(context, model_id, disable_thinking):
            full_response += chunk
            now = asyncio.get_event_loop().time()
            if now - last_edit_time >= STREAM_EDIT_INTERVAL:
                # show preview during streaming (last TG_MAX_LENGTH chars)
                preview = full_response[-TG_MAX_LENGTH + 3:] if len(full_response) > TG_MAX_LENGTH else full_response
                try:
                    await reply.edit_text(html.escape(preview) + " ▌")
                    last_edit_time = now
                except Exception:
                    pass

        if not full_response:
            await reply.edit_text("⚠️ The model returned an empty response.")
            return

        parts = _split_text(full_response)
        await _send_formatted(reply, parts[0])
        for part in parts[1:]:
            await _answer_formatted(message, part)

    except Exception as e:
        error_str = str(e)
        logger.error("LLM error for user %s model %s: %s", db_user.id, model_key, error_str)

        if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower() or "resource_exhausted" in error_str.lower():
            await reply.edit_text(
                f"⏳ <b>Model is overloaded</b>\n\n"
                f"<b>{model_cfg.name}</b> has reached its request limit.\n\n"
                f"Choose another model 👇",
                parse_mode="HTML",
                reply_markup=models_keyboard(model_key),
            )
        elif "402" in error_str or "insufficient balance" in error_str.lower() or "payment required" in error_str.lower():
            await reply.edit_text(
                f"💳 <b>Model temporarily unavailable</b>\n\n"
                f"<b>{model_cfg.name}</b> is not available right now due to provider limits.\n\n"
                f"Choose another model 👇",
                parse_mode="HTML",
                reply_markup=models_keyboard(model_key),
            )
        elif "decommissioned" in error_str or "not supported" in error_str:
            await reply.edit_text(
                f"❌ <b>Model unavailable</b>\n\n"
                f"<b>{model_cfg.name}</b> was decommissioned by the provider.\n\n"
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
        else:
            await reply.edit_text(
                f"⚠️ <b>Model error</b>\n\n"
                f"Try again or choose a different model 👇",
                parse_mode="HTML",
                reply_markup=models_keyboard(model_key),
            )
        return

    await add_message(db_session, conv.id, "assistant", full_response)
