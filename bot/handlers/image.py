import logging
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession
from config import IMAGE_COST_CREDITS
from db.models import User
from db.repository import spend_credits
from llm.image_gen import generate_image, ImageGenerationError

router = Router()
logger = logging.getLogger(__name__)

_pending_image_users: set[int] = set()


def _extension_for_mime(mime_type: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
    }.get(mime_type, "png")


def _is_waiting_for_image(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in _pending_image_users)


async def _show_image_help(message: Message, waiting: bool = False) -> None:
    if waiting:
        text = (
            "🎨 <b>Опишите картинку одним сообщением</b>\n\n"
            "Например: <code>кот-космонавт на Луне</code>\n\n"
            f"Стоимость: <b>{IMAGE_COST_CREDITS}</b> запроса"
        )
    else:
        text = (
            "🎨 <b>Генерация картинок</b>\n\n"
            "Отправьте команду:\n"
            "<code>/image кот-космонавт на Луне</code>\n\n"
            f"Стоимость: <b>{IMAGE_COST_CREDITS}</b> запроса за картинку"
        )
    await message.answer(text, parse_mode="HTML")


async def _generate_and_send(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    prompt: str,
) -> None:
    if len(prompt) > 1000:
        await message.answer("❌ Описание слишком длинное. Максимум 1000 символов.")
        return

    if db_user.credits < IMAGE_COST_CREDITS and not db_user.has_unlimited_access:
        await message.answer(
            f"❌ <b>Недостаточно запросов</b>\n\n"
            f"Генерация картинки стоит <b>{IMAGE_COST_CREDITS}</b> запроса.\n"
            f"У вас: <b>{db_user.credits}</b>\n\n"
            f"Безлимит → /buy",
            parse_mode="HTML",
        )
        return

    status = await message.answer("🎨 Рисую картинку... Подождите 10–30 сек.")
    await message.bot.send_chat_action(message.chat.id, "upload_photo")

    try:
        image_bytes, mime_type = await generate_image(prompt)
    except ImageGenerationError as exc:
        logger.error("Image generation failed for user %s: %s", db_user.id, exc)
        error_text = str(exc)
        if "429" in error_text or "quota" in error_text.lower() or "rate" in error_text.lower():
            user_message = "⏳ Сервис перегружен. Попробуйте через минуту."
        elif "402" in error_text or "insufficient" in error_text.lower() or "credits" in error_text.lower():
            user_message = "💳 Сервис картинок временно недоступен. Попробуйте позже."
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
        logger.exception("Unexpected image generation error for user %s", db_user.id)
        await status.edit_text("⚠️ Не удалось создать картинку. Попробуйте позже.")
        return

    if not db_user.has_unlimited_access:
        spent = await spend_credits(db_session, db_user.id, IMAGE_COST_CREDITS)
        if not spent:
            await status.edit_text("❌ Недостаточно запросов для завершения операции.")
            return

    ext = _extension_for_mime(mime_type)
    caption = f"🎨 {prompt[:900]}"

    try:
        await status.delete()
    except Exception:
        pass

    await message.answer_photo(
        BufferedInputFile(image_bytes, filename=f"image.{ext}"),
        caption=caption,
    )


@router.message(Command("image"))
async def cmd_image(
    message: Message,
    command: CommandObject,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    _pending_image_users.discard(message.from_user.id)
    prompt = (command.args or "").strip()
    if not prompt:
        _pending_image_users.add(message.from_user.id)
        await _show_image_help(message, waiting=True)
        return
    await _generate_and_send(message, db_session, db_user, prompt)


@router.message(F.text == "🎨 Create Image")
async def btn_image(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    _pending_image_users.add(message.from_user.id)
    await _show_image_help(message, waiting=True)


@router.message(F.text, _is_waiting_for_image)
async def image_prompt_followup(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    if not message.text or message.text.startswith("/") or message.text in {
        "💬 New Chat", "🤖 Models", "💰 Balance", "👥 Referral", "💎 Subscription", "🎨 Create Image",
    }:
        _pending_image_users.discard(message.from_user.id)
        return

    _pending_image_users.discard(message.from_user.id)
    await _generate_and_send(message, db_session, db_user, message.text.strip())
