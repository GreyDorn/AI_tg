import logging
from collections.abc import Awaitable, Callable
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession
from config import IMAGE_COST_CREDITS, IMAGE_FREE_COST_CREDITS
from db.models import User
from db.repository import spend_credits
from llm.image_gen import generate_image, generate_image_free, ImageGenerationError

router = Router()
logger = logging.getLogger(__name__)

MENU_BUTTONS = {
    "💬 New Chat", "🤖 Models", "💰 Balance", "👥 Referral", "💎 Subscription",
    "🎨 Create Image", "🆓 Free Image",
}

_pending_image_mode: dict[int, str] = {}


def _extension_for_mime(mime_type: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
    }.get(mime_type, "png")


def _is_waiting_for_image(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in _pending_image_mode)


async def _show_image_help(message: Message, mode: str, waiting: bool = False) -> None:
    if mode == "free":
        cost_line = "Бесплатно, без списания запросов"
        command = "/imagefree кот-космонавт на Луне"
        title = "🆓 <b>Бесплатная генерация картинок</b>"
        quality = "Качество ниже, чем у /image, но полностью бесплатно."
    else:
        cost_line = f"Стоимость: <b>{IMAGE_COST_CREDITS}</b> запроса"
        command = "/image кот-космонавт на Луне"
        title = "🎨 <b>Генерация картинок (HD)</b>"
        quality = "Лучшее качество через Gemini / Flux."

    if waiting:
        text = (
            f"{title}\n\n"
            f"Опишите картинку одним сообщением.\n"
            f"Например: <code>кот-космонавт на Луне</code>\n\n"
            f"{cost_line}\n"
            f"{quality}"
        )
    else:
        text = (
            f"{title}\n\n"
            f"Отправьте команду:\n"
            f"<code>{command}</code>\n\n"
            f"{cost_line}\n"
            f"{quality}"
        )
    await message.answer(text, parse_mode="HTML")


async def _generate_and_send(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    prompt: str,
    *,
    mode: str,
    cost: int,
    generator: Callable[[str], Awaitable[tuple[bytes, str]]],
) -> None:
    if len(prompt) > 1000:
        await message.answer("❌ Описание слишком длинное. Максимум 1000 символов.")
        return

    if cost > 0 and db_user.credits < cost and not db_user.has_unlimited_access:
        await message.answer(
            f"❌ <b>Недостаточно запросов</b>\n\n"
            f"Генерация картинки стоит <b>{cost}</b> запроса.\n"
            f"У вас: <b>{db_user.credits}</b>\n\n"
            f"Попробуйте бесплатный вариант → /imagefree\n"
            f"Безлимит → /buy",
            parse_mode="HTML",
        )
        return

    status_text = (
        "🆓 Рисую бесплатную картинку... Подождите 10–40 сек."
        if mode == "free"
        else "🎨 Рисую картинку... Подождите 10–30 сек."
    )
    status = await message.answer(status_text)
    await message.bot.send_chat_action(message.chat.id, "upload_photo")

    try:
        image_bytes, mime_type = await generator(prompt)
    except ImageGenerationError as exc:
        logger.error("Image generation failed mode=%s user=%s: %s", mode, db_user.id, exc)
        error_text = str(exc)
        if "429" in error_text or "quota" in error_text.lower() or "rate" in error_text.lower():
            user_message = "⏳ Сервис перегружен. Попробуйте через минуту."
        elif "402" in error_text or "insufficient" in error_text.lower() or "credits" in error_text.lower():
            user_message = "💳 Платный сервис картинок временно недоступен. Попробуйте /imagefree."
        elif "text instead of image" in error_text.lower():
            user_message = (
                "⚠️ Модель вернула текст вместо картинки.\n"
                "Попробуйте переформулировать описание или повторите запрос."
            )
        else:
            user_message = "⚠️ Не удалось создать картинку. Попробуйте другое описание."
        await status.edit_text(user_message)
        return
    except Exception:
        logger.exception("Unexpected image generation error mode=%s user=%s", mode, db_user.id)
        await status.edit_text("⚠️ Не удалось создать картинку. Попробуйте позже.")
        return

    if cost > 0 and not db_user.has_unlimited_access:
        spent = await spend_credits(db_session, db_user.id, cost)
        if not spent:
            await status.edit_text("❌ Недостаточно запросов для завершения операции.")
            return

    ext = _extension_for_mime(mime_type)
    prefix = "🆓" if mode == "free" else "🎨"
    caption = f"{prefix} {prompt[:900]}"

    try:
        await status.delete()
    except Exception:
        pass

    await message.answer_photo(
        BufferedInputFile(image_bytes, filename=f"image.{ext}"),
        caption=caption,
    )


def _set_image_mode(message: Message, mode: str, prompt: str) -> None:
    user_id = message.from_user.id
    if prompt:
        _pending_image_mode.pop(user_id, None)
    else:
        _pending_image_mode[user_id] = mode


@router.message(Command("image"))
async def cmd_image(
    message: Message,
    command: CommandObject,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    prompt = (command.args or "").strip()
    _set_image_mode(message, "premium", prompt)
    if not prompt:
        await _show_image_help(message, mode="premium", waiting=True)
        return
    await _generate_and_send(
        message, db_session, db_user, prompt,
        mode="premium", cost=IMAGE_COST_CREDITS, generator=generate_image,
    )


@router.message(Command("imagefree"))
async def cmd_image_free(
    message: Message,
    command: CommandObject,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    prompt = (command.args or "").strip()
    _set_image_mode(message, "free", prompt)
    if not prompt:
        await _show_image_help(message, mode="free", waiting=True)
        return
    await _generate_and_send(
        message, db_session, db_user, prompt,
        mode="free", cost=IMAGE_FREE_COST_CREDITS, generator=generate_image_free,
    )


@router.message(F.text == "🎨 Create Image")
async def btn_image(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    _pending_image_mode[message.from_user.id] = "premium"
    await _show_image_help(message, mode="premium", waiting=True)


@router.message(F.text == "🆓 Free Image")
async def btn_image_free(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    _pending_image_mode[message.from_user.id] = "free"
    await _show_image_help(message, mode="free", waiting=True)


@router.message(F.text, _is_waiting_for_image)
async def image_prompt_followup(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    if not message.text or message.text.startswith("/") or message.text in MENU_BUTTONS:
        _pending_image_mode.pop(message.from_user.id, None)
        return

    mode = _pending_image_mode.pop(message.from_user.id, "premium")
    prompt = message.text.strip()
    if mode == "free":
        await _generate_and_send(
            message, db_session, db_user, prompt,
            mode="free", cost=IMAGE_FREE_COST_CREDITS, generator=generate_image_free,
        )
    else:
        await _generate_and_send(
            message, db_session, db_user, prompt,
            mode="premium", cost=IMAGE_COST_CREDITS, generator=generate_image,
        )
