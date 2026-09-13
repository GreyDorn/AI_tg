"""MAX update handlers."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from config import DEFAULT_MODEL, MODELS, MONETIZATION_ENABLED, LLM_GATEWAY_URL, resolve_model_key
from db.repository import (
    SessionFactory,
    get_or_create_user,
    clear_waiting_modes,
    update_user_model,
    update_user_image_model,
    create_conversation,
    get_active_conversation,
    clear_conversation_messages,
)
from core.chat import (
    setup_text_chat,
    save_assistant_message,
    setup_vision_chat,
    revert_user_model,
)
from core.credits import refund
from core.types import LlmErrorKind
from max_bot.api import send_message, edit_message, answer_callback
from max_bot.gateway_client import GatewayError, complete_chat, complete_vision
from max_bot.keyboards import models_keyboard, main_menu_keyboard
from max_bot.media import find_image_url, download_bytes
from max_bot.processing_lock import try_acquire, release
from max_bot.admin import handle_stats
from max_bot.images import (
    extract_image_intent_prompt,
    show_image_models,
    generate_and_send,
    select_image_model,
    set_image_waiting,
    resolve_max_image_model_key,
    ensure_free_image_model,
)

logger = logging.getLogger(__name__)

WELCOME = (
    "Привет! Я AI-ассистент с моделями ChatGPT, DeepSeek, Gemini и Groq.\n\n"
    "• Напишите сообщение или отправьте фото с подписью\n"
    "• «Модели чата» — выбор нейросети для текста\n"
    "• «Модели картинок» / «Создать картинку» — генерация изображений"
)


@dataclass
class Sender:
    user_id: int
    full_name: str
    username: str | None


def _sender_from_dict(data: dict) -> Sender | None:
    user_id = data.get("user_id")
    if user_id is None:
        return None
    name = (data.get("name") or data.get("first_name") or "Пользователь").strip()
    return Sender(int(user_id), name, data.get("username"))


def _extract_message(update: dict) -> tuple[Sender | None, str, list[dict]]:
    if update.get("update_type") != "message_created":
        return None, "", []

    message = update.get("message") or {}
    body = message.get("body") or {}
    sender = message.get("sender") or {}
    if sender.get("is_bot"):
        return None, "", []

    person = _sender_from_dict(sender)
    if person is None:
        return None, "", []

    text = (body.get("text") or "").strip()
    attachments = body.get("attachments") or []
    if not isinstance(attachments, list):
        attachments = []
    return person, text, attachments


def _extract_callback(update: dict) -> tuple[str | None, str | None, Sender | None]:
    if update.get("update_type") != "message_callback":
        return None, None, None

    callback = update.get("callback") or {}
    message = update.get("message") or {}
    sender = callback.get("user") or message.get("sender") or {}
    person = _sender_from_dict(sender)
    return (
        callback.get("callback_id"),
        callback.get("payload"),
        person,
    )


def _extract_bot_started(update: dict) -> Sender | None:
    if update.get("update_type") != "bot_started":
        return None
    return _sender_from_dict(update.get("user") or {})


def _models_text(current_key: str) -> str:
    current = MODELS[current_key]
    if MONETIZATION_ENABLED:
        return f"Выберите модель.\nТекущая: <b>{current.name}</b>"
    return f"Выберите модель (бесплатно).\nТекущая: {current.name}"


def _error_text(kind: LlmErrorKind, *, vision: bool = False) -> str:
    if kind == LlmErrorKind.VISION_UNAVAILABLE:
        return "📷 Анализ фото временно недоступен. Попробуйте позже."
    if kind == LlmErrorKind.VISION_FAILED:
        return "❌ Не удалось разобрать фото. Попробуйте другое изображение или подпись короче."
    if kind == LlmErrorKind.RATE_LIMITED:
        return "⏳ Модель перегружена. Подождите или выберите другую в «Модели»."
    if kind == LlmErrorKind.PROVIDER_LIMIT:
        return "⚠️ У провайдера закончился лимит. Выберите другую модель."
    if kind == LlmErrorKind.CONTEXT_TOO_LARGE:
        return "Сообщение слишком длинное. Нажмите «Новый чат» и попробуйте короче."
    if vision:
        return "❌ Не удалось обработать фото. Попробуйте ещё раз."
    return "❌ Не удалось получить ответ. Попробуйте ещё раз или смените модель."


async def _reply(user_id: int, text: str, *, keyboard: list[dict] | None = None) -> None:
    attachments = keyboard or main_menu_keyboard()
    await send_message(user_id=user_id, text=text, attachments=attachments)


async def _send_status(user_id: int, text: str) -> str | None:
    return await send_message(user_id=user_id, text=text)


async def _finish_status(
    user_id: int,
    status_id: str | None,
    text: str,
    *,
    keyboard: list[dict] | None = None,
) -> None:
    attachments = keyboard or main_menu_keyboard()
    if status_id and await edit_message(status_id, text, attachments=attachments):
        return
    await send_message(user_id=user_id, text=text, attachments=attachments)


async def _show_models(user_id: int, current_key: str) -> None:
    await send_message(
        user_id=user_id,
        text=_models_text(current_key),
        attachments=models_keyboard(current_key),
    )


async def _handle_clear(sender: Sender) -> None:
    async with SessionFactory() as session:
        user, _ = await get_or_create_user(
            session, sender.user_id, sender.full_name, sender.username, language_code="ru",
        )
        conv = await get_active_conversation(session, user.id)
        if conv:
            await clear_conversation_messages(session, conv.id)
        await clear_waiting_modes(session, user.id)
    await _reply(sender.user_id, "Контекст очищен. Можете начать новый диалог.")


async def _handle_model_select(sender: Sender, model_key: str) -> None:
    model_key = resolve_model_key(model_key)
    async with SessionFactory() as session:
        user, _ = await get_or_create_user(
            session, sender.user_id, sender.full_name, sender.username, language_code="ru",
        )
        await clear_waiting_modes(session, user.id)
        if model_key != resolve_model_key(user.current_model):
            await update_user_model(session, user.id, model_key)
            await create_conversation(session, user.id, model_key)
            user.current_model = model_key
        current = model_key
    await _show_models(sender.user_id, current)


async def _handle_callback(callback_id: str | None, payload: str | None, sender: Sender | None) -> None:
    if not sender or not payload:
        return

    if callback_id:
        await answer_callback(callback_id)

    if payload == "menu:models":
        async with SessionFactory() as session:
            user, _ = await get_or_create_user(
                session, sender.user_id, sender.full_name, sender.username, language_code="ru",
            )
            current = resolve_model_key(user.current_model)
        await _show_models(sender.user_id, current)
        return

    if payload == "menu:clear":
        await _handle_clear(sender)
        return

    if payload == "menu:image_models":
        async with SessionFactory() as session:
            user, _ = await get_or_create_user(
                session, sender.user_id, sender.full_name, sender.username, language_code="ru",
            )
            current = resolve_max_image_model_key(user.current_image_model)
            if current != user.current_image_model:
                await update_user_image_model(session, user.id, current)
            await set_image_waiting(session, user, True)
        await show_image_models(sender.user_id, current)
        return

    if payload == "menu:create_image":
        async with SessionFactory() as session:
            user, _ = await get_or_create_user(
                session, sender.user_id, sender.full_name, sender.username, language_code="ru",
            )
            await set_image_waiting(session, user, True)
            from max_bot.keyboards import cancel_image_keyboard
            _, model_cfg = await ensure_free_image_model(session, user)
            await send_message(
                user_id=sender.user_id,
                text=f"Опишите, что нарисовать.\nМодель: {model_cfg.name}",
                attachments=cancel_image_keyboard(),
            )
        return

    if payload == "cancel:image":
        async with SessionFactory() as session:
            user, _ = await get_or_create_user(
                session, sender.user_id, sender.full_name, sender.username, language_code="ru",
            )
            if user.waiting_for_image:
                await set_image_waiting(session, user, False)
                await _reply(sender.user_id, "Режим создания картинки отменён.")
            else:
                await _reply(sender.user_id, "Нечего отменять.")
        return

    if payload.startswith("imagemodel:"):
        async with SessionFactory() as session:
            user, _ = await get_or_create_user(
                session, sender.user_id, sender.full_name, sender.username, language_code="ru",
            )
            await select_image_model(sender.user_id, session, user, payload.split(":", 1)[1])
        return

    if payload.startswith("model:"):
        await _handle_model_select(sender, payload.split(":", 1)[1])
        return


async def _handle_chat(sender: Sender, text: str, *, operation_key: str | None = None) -> None:
    if not await try_acquire(sender.user_id):
        return
    try:
        async with SessionFactory() as session:
            user, _ = await get_or_create_user(
                session, sender.user_id, sender.full_name, sender.username, language_code="ru",
            )
            await clear_waiting_modes(session, user.id)

            setup = await setup_text_chat(session, user, text, operation_key=operation_key)
            if setup is None:
                await _reply(sender.user_id, "Недостаточно запросов.")
                return

            messages = [{"role": m.role, "content": m.content} for m in setup.context]
            user_id = user.id

        status_id = await _send_status(sender.user_id, "⏳")

        try:
            answer = await complete_chat(setup.model_key, messages)
        except GatewayError as exc:
            async with SessionFactory() as session:
                if setup.credits_spent:
                    await refund(session, user_id, setup.credits_spent)
            await _finish_status(sender.user_id, status_id, _error_text(exc.kind))
            return
        except Exception:
            logger.exception("Gateway chat failed user=%s", sender.user_id)
            async with SessionFactory() as session:
                if setup.credits_spent:
                    await refund(session, user_id, setup.credits_spent)
            await _finish_status(sender.user_id, status_id, _error_text(LlmErrorKind.GENERIC))
            return

        async with SessionFactory() as session:
            await save_assistant_message(session, setup.conv_id, answer)

        await _finish_status(sender.user_id, status_id, answer)
    finally:
        release(sender.user_id)


async def _handle_vision(
    sender: Sender,
    text: str,
    attachments: list[dict],
    *,
    operation_key: str | None = None,
) -> None:
    if not LLM_GATEWAY_URL:
        await _reply(sender.user_id, "📷 Анализ фото недоступен (шлюз не настроен).")
        return

    image_url, mime_type = find_image_url(attachments)
    if not image_url:
        await _reply(
            sender.user_id,
            "📷 Не удалось получить фото. Попробуйте отправить изображение ещё раз.",
        )
        return

    try:
        image_bytes = await download_bytes(image_url)
    except ValueError:
        await _reply(sender.user_id, "📷 Фото слишком большое (макс. 4 МБ).")
        return
    except Exception:
        logger.exception("Image download failed user=%s url=%s", sender.user_id, image_url[:120])
        await _reply(sender.user_id, _error_text(LlmErrorKind.VISION_FAILED, vision=True))
        return

    if not await try_acquire(sender.user_id):
        return
    try:
        async with SessionFactory() as session:
            user, _ = await get_or_create_user(
                session, sender.user_id, sender.full_name, sender.username, language_code="ru",
            )
            await clear_waiting_modes(session, user.id)

            setup = await setup_vision_chat(
                session,
                user,
                caption=text or None,
                image_bytes=image_bytes,
                mime_type=mime_type,
                operation_key=operation_key,
            )
            if setup is None:
                await _reply(sender.user_id, "Недостаточно запросов.")
                return

            context = [{"role": m.role, "content": m.content} for m in setup.context]
            vision_name = setup.vision_name
            conv_id = setup.conv_id
            revert_model_key = setup.revert_model_key
            credits_spent = setup.credits_spent
            vision_key = setup.vision_key
            prompt = setup.prompt

        status_id = await _send_status(
            sender.user_id,
            f"📷 Анализирую через {vision_name}…",
        )

        try:
            answer = await complete_vision(
                vision_key,
                context,
                image_bytes=image_bytes,
                mime_type=mime_type,
                prompt=prompt,
            )
        except GatewayError as exc:
            async with SessionFactory() as session:
                user, _ = await get_or_create_user(
                    session, sender.user_id, sender.full_name, sender.username, language_code="ru",
                )
                await revert_user_model(session, user, revert_model_key)
                if credits_spent:
                    await refund(session, user.id, credits_spent)
            await _finish_status(sender.user_id, status_id, _error_text(exc.kind, vision=True))
            return
        except Exception:
            logger.exception("Gateway vision failed user=%s", sender.user_id)
            async with SessionFactory() as session:
                user, _ = await get_or_create_user(
                    session, sender.user_id, sender.full_name, sender.username, language_code="ru",
                )
                await revert_user_model(session, user, revert_model_key)
                if credits_spent:
                    await refund(session, user.id, credits_spent)
            await _finish_status(sender.user_id, status_id, _error_text(LlmErrorKind.GENERIC, vision=True))
            return

        async with SessionFactory() as session:
            await save_assistant_message(session, conv_id, answer)

        await _finish_status(sender.user_id, status_id, answer)
    finally:
        release(sender.user_id)


async def _handle_command(sender: Sender, text: str, *, event_key: str | None = None) -> bool:
    low = text.lower().strip()

    if low in ("/start", "start", "старт", "привет"):
        async with SessionFactory() as session:
            await get_or_create_user(
                session, sender.user_id, sender.full_name, sender.username, language_code="ru",
            )
        await _reply(sender.user_id, WELCOME)
        return True

    if low in ("/help", "help", "помощь"):
        await _reply(
            sender.user_id,
            "Текст — обычный чат.\n"
            "Фото с подписью — распознавание.\n"
            "«Модели чата» — LLM для текста.\n"
            "«Модели картинок» — выбор Flux, Turbo и др.\n"
            "«Создать картинку» — опишите, что нарисовать.\n"
            "Или напишите: нарисуй закат над морем",
        )
        return True

    if low in ("/imagemodels", "модели картинок"):
        async with SessionFactory() as session:
            user, _ = await get_or_create_user(
                session, sender.user_id, sender.full_name, sender.username, language_code="ru",
            )
            current = resolve_max_image_model_key(user.current_image_model)
            if current != user.current_image_model:
                await update_user_image_model(session, user.id, current)
            await set_image_waiting(session, user, True)
        await show_image_models(sender.user_id, current)
        return True

    if low.startswith("/image"):
        parts = text.split(maxsplit=1)
        prompt = parts[1].strip() if len(parts) > 1 else ""
        async with SessionFactory() as session:
            user, _ = await get_or_create_user(
                session, sender.user_id, sender.full_name, sender.username, language_code="ru",
            )
            if not prompt:
                await set_image_waiting(session, user, True)
                from max_bot.keyboards import cancel_image_keyboard
                _, model_cfg = await ensure_free_image_model(session, user)
                await send_message(
                    user_id=sender.user_id,
                    text=f"Опишите, что нарисовать.\nМодель: {model_cfg.name}",
                    attachments=cancel_image_keyboard(),
                )
            else:
                if not await try_acquire(sender.user_id):
                    return True
                try:
                    await generate_and_send(
                        sender.user_id, session, user, prompt, operation_key=event_key,
                    )
                finally:
                    release(sender.user_id)
        return True

    if low in ("/models", "models", "модели"):
        async with SessionFactory() as session:
            user, _ = await get_or_create_user(
                session, sender.user_id, sender.full_name, sender.username, language_code="ru",
            )
            current = resolve_model_key(user.current_model)
        await _show_models(sender.user_id, current)
        return True

    if low.startswith("/model"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await _show_models(sender.user_id, DEFAULT_MODEL)
            return True
        await _handle_model_select(sender, parts[1].strip())
        return True

    if low in ("/clear", "clear", "новый чат"):
        await _handle_clear(sender)
        return True

    if low in ("/stats", "stats", "статистика"):
        await handle_stats(sender.user_id)
        return True

    return False


async def process_update(update: dict, *, event_key: str | None = None) -> None:
    started = _extract_bot_started(update)
    if started is not None:
        async with SessionFactory() as session:
            await get_or_create_user(
                session, started.user_id, started.full_name, started.username, language_code="ru",
            )
        await _reply(started.user_id, WELCOME)
        return

    callback_id, payload, callback_sender = _extract_callback(update)
    if payload is not None:
        await _handle_callback(callback_id, payload, callback_sender)
        return

    sender, text, attachments = _extract_message(update)
    if sender is None:
        return

    image_url, _ = find_image_url(attachments)
    if image_url:
        await _handle_vision(sender, text, attachments, operation_key=event_key)
        return

    if not text:
        return

    intent_prompt = extract_image_intent_prompt(text)
    if intent_prompt:
        async with SessionFactory() as session:
            user, _ = await get_or_create_user(
                session, sender.user_id, sender.full_name, sender.username, language_code="ru",
            )
            if not await try_acquire(sender.user_id):
                return
            try:
                await generate_and_send(
                    sender.user_id, session, user, intent_prompt, operation_key=event_key,
                )
            finally:
                release(sender.user_id)
        return

    async with SessionFactory() as session:
        user, _ = await get_or_create_user(
            session, sender.user_id, sender.full_name, sender.username, language_code="ru",
        )
        if user.waiting_for_image:
            if not await try_acquire(sender.user_id):
                return
            try:
                await generate_and_send(
                    sender.user_id, session, user, text, operation_key=event_key,
                )
            finally:
                release(sender.user_id)
            return

    if text.startswith("/") or text.lower() in (
        "start", "старт", "привет", "help", "помощь",
        "models", "модели", "модели чата", "clear", "новый чат",
        "создать картинку", "модели картинок", "stats", "статистика",
    ):
        if await _handle_command(sender, text, event_key=event_key):
            return

    await _handle_chat(sender, text, operation_key=event_key)
