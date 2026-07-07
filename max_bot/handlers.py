"""MAX update handlers."""

from __future__ import annotations

import logging

from config import DEFAULT_MODEL, MODELS, resolve_model_key
from db.repository import SessionFactory, get_or_create_user, clear_waiting_modes
from core.chat import setup_text_chat, save_assistant_message
from core.credits import refund
from core.types import LlmErrorKind
from max_bot.api import send_message
from max_bot.gateway_client import GatewayError, complete_chat

logger = logging.getLogger(__name__)

WELCOME = (
    "Привет! Я AI-ассистент с моделями ChatGPT, DeepSeek, Gemini и Groq.\n\n"
    "Просто напишите сообщение — я отвечу.\n\n"
    "Команды:\n"
    "/help — справка\n"
    "/models — список моделей\n"
    "/model <имя> — сменить модель\n"
    "/clear — очистить контекст диалога"
)

HELP = (
    "Доступные команды:\n"
    "/models — список моделей\n"
    "/model llama-3.3-70b — пример смены модели\n"
    "/clear — начать диалог заново\n\n"
    f"Текущая модель по умолчанию: {MODELS[DEFAULT_MODEL].name}"
)


def _extract_message(update: dict) -> tuple[int | None, str]:
    if update.get("update_type") != "message_created":
        return None, ""

    message = update.get("message") or {}
    body = message.get("body") or {}
    sender = message.get("sender") or {}
    if sender.get("is_bot"):
        return None, ""

    user_id = sender.get("user_id")
    text = (body.get("text") or "").strip()
    if user_id is None:
        return None, ""
    return int(user_id), text


def _extract_bot_started(update: dict) -> int | None:
    if update.get("update_type") != "bot_started":
        return None
    user = update.get("user") or {}
    user_id = user.get("user_id")
    return int(user_id) if user_id is not None else None


def _models_list() -> str:
    lines = ["Доступные модели:"]
    for key, cfg in MODELS.items():
        lines.append(f"• {key} — {cfg.name}")
    lines.append(f"\nПо умолчанию: {DEFAULT_MODEL}")
    lines.append("Сменить: /model <ключ>")
    return "\n".join(lines)


def _error_text(kind: LlmErrorKind) -> str:
    if kind == LlmErrorKind.RATE_LIMITED:
        return "⏳ Модель перегружена. Попробуйте через минуту или смените модель: /models"
    if kind == LlmErrorKind.PROVIDER_LIMIT:
        return "⚠️ У провайдера закончился лимит. Попробуйте другую модель: /models"
    if kind == LlmErrorKind.CONTEXT_TOO_LARGE:
        return "Сообщение слишком длинное. Напишите /clear и попробуйте короче."
    return "❌ Не удалось получить ответ. Попробуйте ещё раз или смените модель: /models"


async def _reply(user_id: int, text: str) -> None:
    await send_message(user_id=user_id, text=text)


async def _handle_command(user_id: int, text: str, full_name: str, username: str | None) -> bool:
    low = text.lower().strip()

    if low in ("/start", "start", "старт", "привет"):
        async with SessionFactory() as session:
            await get_or_create_user(session, user_id, full_name, username, language_code="ru")
        await _reply(user_id, WELCOME)
        return True

    if low in ("/help", "help", "помощь"):
        await _reply(user_id, HELP)
        return True

    if low in ("/models", "models"):
        await _reply(user_id, _models_list())
        return True

    if low.startswith("/model"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await _reply(user_id, "Укажите модель, например:\n/model llama-3.3-70b")
            return True
        model_key = resolve_model_key(parts[1].strip())
        async with SessionFactory() as session:
            user, _ = await get_or_create_user(session, user_id, full_name, username, language_code="ru")
            from db.repository import update_user_model
            await update_user_model(session, user.id, model_key)
        cfg = MODELS[model_key]
        await _reply(user_id, f"Модель изменена: {cfg.name} ({model_key})")
        return True

    if low in ("/clear", "clear"):
        async with SessionFactory() as session:
            user, _ = await get_or_create_user(session, user_id, full_name, username, language_code="ru")
            from db.repository import get_active_conversation, clear_conversation_messages
            conv = await get_active_conversation(session, user.id)
            if conv:
                await clear_conversation_messages(session, conv.id)
            await clear_waiting_modes(session, user.id)
        await _reply(user_id, "Контекст очищен. Можете начать новый диалог.")
        return True

    return False


async def _handle_chat(user_id: int, text: str, full_name: str, username: str | None) -> None:
    async with SessionFactory() as session:
        user, _ = await get_or_create_user(session, user_id, full_name, username, language_code="ru")
        await clear_waiting_modes(session, user.id)

        setup = await setup_text_chat(session, user, text)
        if setup is None:
            await _reply(user_id, "Недостаточно запросов.")  # unlikely with monetization off
            return

        messages = [{"role": m.role, "content": m.content} for m in setup.context]

        try:
            answer = await complete_chat(setup.model_key, messages)
        except GatewayError as exc:
            if setup.credits_spent:
                await refund(session, user.id, setup.credits_spent)
            await _reply(user_id, _error_text(exc.kind))
            return
        except Exception:
            logger.exception("Gateway request failed user=%s", user_id)
            if setup.credits_spent:
                await refund(session, user.id, setup.credits_spent)
            await _reply(user_id, _error_text(LlmErrorKind.GENERIC))
            return

        await save_assistant_message(session, setup.conv_id, answer)

    await _reply(user_id, answer)


async def process_update(update: dict) -> None:
    started_user = _extract_bot_started(update)
    if started_user is not None:
        async with SessionFactory() as session:
            await get_or_create_user(
                session,
                started_user,
                full_name="Пользователь",
                username=None,
                language_code="ru",
            )
        await _reply(started_user, WELCOME)
        return

    user_id, text = _extract_message(update)
    if user_id is None or not text:
        return

    message = update.get("message") or {}
    sender = message.get("sender") or {}
    full_name = (sender.get("name") or sender.get("first_name") or "Пользователь").strip()
    username = sender.get("username")

    if text.startswith("/") or text.lower() in (
        "start", "старт", "привет", "help", "помощь", "models", "clear",
    ):
        handled = await _handle_command(user_id, text, full_name, username)
        if handled:
            return

    await _handle_chat(user_id, text, full_name, username)
