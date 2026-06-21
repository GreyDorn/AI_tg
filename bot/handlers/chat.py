import asyncio
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


@router.message(F.text & ~F.text.startswith("/") & ~F.text.in_({"💬 Новый чат", "🤖 Модели", "💰 Баланс", "👥 Реферал", "💳 Купить кредиты"}))
async def handle_message(message: Message, db_session: AsyncSession, db_user: User) -> None:
    model_key = db_user.current_model
    model_cfg = MODELS[model_key]

    if db_user.credits < model_cfg.cost_per_message and not db_user.is_unlimited:
        await message.answer(
            f"❌ <b>Недостаточно кредитов</b>\n\n"
            f"У тебя: <b>{db_user.credits}🔥</b>\n"
            f"Нужно: <b>{model_cfg.cost_per_message}🔥</b>\n\n"
            f"Нажми <b>💰 Баланс</b>, чтобы пополнить.",
            parse_mode="HTML",
        )
        return

    conv = await get_active_conversation(db_session, db_user.id)
    if not conv:
        conv = await create_conversation(db_session, db_user.id, model_key)

    await add_message(db_session, conv.id, "user", message.text)

    all_messages = await get_conversation_messages(db_session, conv.id)
    context = all_messages[-MAX_CONTEXT_MESSAGES:]

    await spend_credits(db_session, db_user.id, model_cfg.cost_per_message) if not db_user.is_unlimited else None
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
                # Показываем только первые TG_MAX_LENGTH символов во время стриминга
                preview = full_response[-TG_MAX_LENGTH + 3:] if len(full_response) > TG_MAX_LENGTH else full_response
                try:
                    await reply.edit_text(preview + " ▌")
                    last_edit_time = now
                except Exception:
                    pass

        if not full_response:
            await reply.edit_text("⚠️ Пустой ответ от модели.")
            return

        # Разбиваем финальный ответ на части если длиннее лимита
        parts = _split_text(full_response)
        await reply.edit_text(parts[0])
        for part in parts[1:]:
            await message.answer(part)

    except Exception as e:
        error_str = str(e)
        logger.error("LLM error for user %s model %s: %s", db_user.id, model_key, error_str)

        if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
            await reply.edit_text(
                f"⏳ <b>Модель временно перегружена</b>\n\n"
                f"<b>{model_cfg.name}</b> исчерпала лимит запросов.\n\n"
                f"Выбери другую модель 👇",
                parse_mode="HTML",
                reply_markup=models_keyboard(model_key),
            )
        elif "decommissioned" in error_str or "not supported" in error_str:
            await reply.edit_text(
                f"❌ <b>Модель недоступна</b>\n\n"
                f"<b>{model_cfg.name}</b> была отключена провайдером.\n\n"
                f"Выбери другую модель 👇",
                parse_mode="HTML",
                reply_markup=models_keyboard(model_key),
            )
        elif "too large" in error_str.lower() or "entity too large" in error_str.lower() or "context" in error_str.lower():
            await reply.edit_text(
                f"📝 <b>Контекст диалога слишком большой</b>\n\n"
                f"Начни новый чат командой /newchat или кнопкой <b>💬 Новый чат</b> — "
                f"это очистит историю и позволит продолжить.",
                parse_mode="HTML",
            )
        else:
            await reply.edit_text(
                f"⚠️ <b>Ошибка модели</b>\n\n"
                f"Попробуй ещё раз или выбери другую модель 👇",
                parse_mode="HTML",
                reply_markup=models_keyboard(model_key),
            )
        return

    await add_message(db_session, conv.id, "assistant", full_response)
