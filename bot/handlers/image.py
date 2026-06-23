import logging
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession
from config import IMAGE_MODELS, DEFAULT_IMAGE_MODEL
from db.models import User
from db.repository import spend_credits, update_user_image_model
from llm.image_gen import generate_image, ImageGenerationError
from bot.keyboards.main import image_models_keyboard

router = Router()
logger = logging.getLogger(__name__)

MENU_BUTTONS = {
    "💬 New Chat", "🤖 Models", "💰 Balance", "👥 Referral", "💎 Subscription",
    "🎨 Create Image", "🖼 Image Models",
}

_pending_image_users: set[int] = set()


def _extension_for_mime(mime_type: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
    }.get(mime_type, "png")


def _is_waiting_for_image(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in _pending_image_users)


def _get_image_model(db_user: User) -> tuple[str, object]:
    model_key = db_user.current_image_model
    if model_key not in IMAGE_MODELS:
        model_key = DEFAULT_IMAGE_MODEL
    return model_key, IMAGE_MODELS[model_key]


async def _show_image_help(message: Message, db_user: User, waiting: bool = False) -> None:
    model_key, model_cfg = _get_image_model(db_user)
    cost = (
        "бесплатно"
        if model_cfg.cost_per_image == 0
        else f"{model_cfg.cost_per_image} запроса"
    )

    if waiting:
        text = (
            f"🎨 <b>Опишите картинку одним сообщением</b>\n\n"
            f"Модель: <b>{model_cfg.name}</b> ({cost})\n"
            f"Например: <code>кот-космонавт на Луне</code>\n\n"
            f"Сменить модель → /imagemodels"
        )
    else:
        text = (
            f"🎨 <b>Генерация картинок</b>\n\n"
            f"Модель: <b>{model_cfg.name}</b> ({cost})\n\n"
            f"Отправьте команду:\n"
            f"<code>/image кот-космонавт на Луне</code>\n\n"
            f"Сменить модель → /imagemodels"
        )
    await message.answer(text, parse_mode="HTML", reply_markup=image_models_keyboard(model_key))


async def _generate_and_send(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    prompt: str,
) -> None:
    if db_user.current_image_model not in IMAGE_MODELS:
        db_user.current_image_model = DEFAULT_IMAGE_MODEL
        await update_user_image_model(db_session, db_user.id, DEFAULT_IMAGE_MODEL)

    model_key, model_cfg = _get_image_model(db_user)
    cost = model_cfg.cost_per_image

    if len(prompt) > 1000:
        await message.answer("❌ Описание слишком длинное. Максимум 1000 символов.")
        return

    if cost > 0 and db_user.credits < cost and not db_user.has_unlimited_access:
        await message.answer(
            f"❌ <b>Недостаточно запросов</b>\n\n"
            f"Модель <b>{model_cfg.name}</b> стоит <b>{cost}</b> запроса.\n"
            f"У вас: <b>{db_user.credits}</b>\n\n"
            f"Выберите бесплатную модель → /imagemodels\n"
            f"Безлимит → /buy",
            parse_mode="HTML",
            reply_markup=image_models_keyboard(model_key),
        )
        return

    status = await message.answer(
        f"🎨 Рисую через <b>{model_cfg.name}</b>... Подождите 10–40 сек.",
        parse_mode="HTML",
    )
    await message.bot.send_chat_action(message.chat.id, "upload_photo")

    try:
        image_bytes, mime_type = await generate_image(prompt, model_key)
    except ImageGenerationError as exc:
        logger.error("Image generation failed user=%s model=%s: %s", db_user.id, model_key, exc)
        error_text = str(exc)
        if "429" in error_text or "quota" in error_text.lower() or "rate" in error_text.lower():
            user_message = "⏳ Сервис перегружен. Попробуйте через минуту."
        elif "402" in error_text or "insufficient" in error_text.lower() or "credits" in error_text.lower():
            user_message = (
                f"💳 Модель <b>{model_cfg.name}</b> временно недоступна.\n\n"
                f"Выберите бесплатную модель → /imagemodels"
            )
        elif "text instead of image" in error_text.lower():
            user_message = (
                "⚠️ Модель вернула текст вместо картинки.\n"
                "Попробуйте переформулировать описание."
            )
        else:
            user_message = "⚠️ Не удалось создать картинку. Попробуйте другую модель → /imagemodels"
        await status.edit_text(user_message, parse_mode="HTML", reply_markup=image_models_keyboard(model_key))
        return
    except Exception:
        logger.exception("Unexpected image generation error user=%s model=%s", db_user.id, model_key)
        await status.edit_text("⚠️ Не удалось создать картинку. Попробуйте позже.")
        return

    if cost > 0 and not db_user.has_unlimited_access:
        spent = await spend_credits(db_session, db_user.id, cost)
        if not spent:
            await status.edit_text("❌ Недостаточно запросов для завершения операции.")
            return

    ext = _extension_for_mime(mime_type)
    caption = f"🎨 {model_cfg.name}\n{prompt[:850]}"

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
    prompt = (command.args or "").strip()
    if not prompt:
        _pending_image_users.add(message.from_user.id)
        await _show_image_help(message, db_user, waiting=True)
        return
    _pending_image_users.discard(message.from_user.id)
    await _generate_and_send(message, db_session, db_user, prompt)


@router.message(F.text == "🎨 Create Image")
async def btn_image(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    _pending_image_users.add(message.from_user.id)
    await _show_image_help(message, db_user, waiting=True)


@router.message(F.text, _is_waiting_for_image)
async def image_prompt_followup(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    if not message.text or message.text.startswith("/") or message.text in MENU_BUTTONS:
        _pending_image_users.discard(message.from_user.id)
        return

    _pending_image_users.discard(message.from_user.id)
    await _generate_and_send(message, db_session, db_user, message.text.strip())
