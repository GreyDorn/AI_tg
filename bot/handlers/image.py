import logging
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, BufferedInputFile, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from config import IMAGE_MODELS
from db.models import User
from db.repository import spend_credits, update_user_image_model
from llm.image_gen import generate_image, ImageGenerationError
from llm.provider_status import resolve_image_model_key
from bot.keyboards.main import image_models_keyboard, cancel_keyboard

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


def _format_cost(cost: int) -> str:
    if cost == 0:
        return "free"
    if cost == 1:
        return "1 request"
    return f"{cost} requests"


def _get_image_model(db_user: User) -> tuple[str, object]:
    model_key = resolve_image_model_key(db_user.current_image_model)
    return model_key, IMAGE_MODELS[model_key]


async def _show_image_help(message: Message, db_user: User, waiting: bool = False) -> None:
    model_key, model_cfg = _get_image_model(db_user)
    cost = _format_cost(model_cfg.cost_per_image)

    if waiting:
        text = (
            f"🎨 <b>Describe your image in one message</b>\n\n"
            f"Model: <b>{model_cfg.name}</b> ({cost})\n"
            f"Example: <code>astronaut cat on the Moon</code>\n\n"
            f"Change model → /imagemodels"
        )
    else:
        text = (
            f"🎨 <b>Image Generation</b>\n\n"
            f"Model: <b>{model_cfg.name}</b> ({cost})\n\n"
            f"Send a command:\n"
            f"<code>/image astronaut cat on the Moon</code>\n\n"
            f"Change model → /imagemodels"
        )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=cancel_keyboard() if waiting else image_models_keyboard(model_key),
    )


async def _generate_and_send(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    prompt: str,
) -> None:
    model_key, model_cfg = _get_image_model(db_user)
    if model_key != db_user.current_image_model:
        db_user.current_image_model = model_key
        await update_user_image_model(db_session, db_user.id, model_key)
    cost = model_cfg.cost_per_image

    if len(prompt) > 1000:
        await message.answer("❌ Description is too long. Maximum 1000 characters.")
        return

    if cost > 0 and db_user.credits < cost and not db_user.has_unlimited_access:
        await message.answer(
            f"❌ <b>Not enough requests</b>\n\n"
            f"<b>{model_cfg.name}</b> costs <b>{cost}</b> requests.\n"
            f"You have: <b>{db_user.credits}</b>\n\n"
            f"Try a free model → /imagemodels\n"
            f"Unlimited access → /buy",
            parse_mode="HTML",
            reply_markup=image_models_keyboard(model_key),
        )
        return

    status = await message.answer(
        f"🎨 Drawing with <b>{model_cfg.name}</b>... Please wait 10–40 sec.",
        parse_mode="HTML",
    )
    await message.bot.send_chat_action(message.chat.id, "upload_photo")

    try:
        image_bytes, mime_type = await generate_image(prompt, model_key)
    except ImageGenerationError as exc:
        logger.error("Image generation failed user=%s model=%s: %s", db_user.id, model_key, exc)
        error_text = str(exc)
        if "429" in error_text or "quota" in error_text.lower() or "rate" in error_text.lower():
            user_message = "⏳ Service is busy. Please try again in a minute."
        elif "402" in error_text or "insufficient" in error_text.lower() or "credits" in error_text.lower():
            user_message = (
                f"💳 <b>{model_cfg.name}</b> is temporarily unavailable.\n\n"
                f"Try a free model → /imagemodels"
            )
        elif "text instead of image" in error_text.lower():
            user_message = (
                "⚠️ The model returned text instead of an image.\n"
                "Try rephrasing your description."
            )
        else:
            user_message = "⚠️ Could not create the image. Try another model → /imagemodels"
        await status.edit_text(user_message, parse_mode="HTML", reply_markup=image_models_keyboard(model_key))
        return
    except Exception:
        logger.exception("Unexpected image generation error user=%s model=%s", db_user.id, model_key)
        await status.edit_text("⚠️ Could not create the image. Please try again later.")
        return

    if cost > 0 and not db_user.has_unlimited_access:
        spent = await spend_credits(db_session, db_user.id, cost)
        if not spent:
            await status.edit_text("❌ Not enough requests to complete this action.")
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


@router.callback_query(F.data == "cancel")
async def cancel_image_prompt(callback: CallbackQuery) -> None:
    if not callback.from_user or callback.from_user.id not in _pending_image_users:
        await callback.answer("Nothing to cancel.")
        return
    _pending_image_users.discard(callback.from_user.id)
    await callback.message.edit_text("❌ Image generation cancelled.")
    await callback.answer()


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
