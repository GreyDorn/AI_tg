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


def _extension_for_mime(mime_type: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
    }.get(mime_type, "png")


async def _show_image_help(message: Message) -> None:
    await message.answer(
        "🎨 <b>Image generation</b>\n\n"
        "Describe what you want to create:\n"
        "<code>/image a cat astronaut on the Moon</code>\n\n"
        f"Cost: <b>{IMAGE_COST_CREDITS}</b> requests per image",
        parse_mode="HTML",
    )


async def _generate_and_send(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    prompt: str,
) -> None:
    if len(prompt) > 1000:
        await message.answer("❌ Description is too long. Please use up to 1000 characters.")
        return

    if db_user.credits < IMAGE_COST_CREDITS and not db_user.has_unlimited_access:
        await message.answer(
            f"❌ <b>Not enough requests</b>\n\n"
            f"Image generation costs <b>{IMAGE_COST_CREDITS}</b> requests.\n"
            f"You have: <b>{db_user.credits}</b>\n\n"
            f"Get unlimited access → /buy",
            parse_mode="HTML",
        )
        return

    status = await message.answer("🎨 Generating image... Please wait ~10–30 sec.")
    await message.bot.send_chat_action(message.chat.id, "upload_photo")

    try:
        image_bytes, mime_type = await generate_image(prompt)
    except ImageGenerationError as exc:
        logger.error("Image generation failed for user %s: %s", db_user.id, exc)
        error_text = str(exc)
        if "429" in error_text or "quota" in error_text.lower() or "rate" in error_text.lower():
            user_message = "⏳ Image service is overloaded. Try again in a minute."
        elif "402" in error_text or "insufficient" in error_text.lower():
            user_message = "💳 Image service is temporarily unavailable."
        else:
            user_message = "⚠️ Could not generate the image. Try a different description."
        await status.edit_text(user_message)
        return
    except Exception:
        logger.exception("Unexpected image generation error for user %s", db_user.id)
        await status.edit_text("⚠️ Could not generate the image. Try again later.")
        return

    if not db_user.has_unlimited_access:
        spent = await spend_credits(db_session, db_user.id, IMAGE_COST_CREDITS)
        if not spent:
            await status.edit_text("❌ Not enough requests to complete the operation.")
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
    prompt = (command.args or "").strip()
    if not prompt:
        await _show_image_help(message)
        return
    await _generate_and_send(message, db_session, db_user, prompt)


@router.message(F.text == "🎨 Create Image")
async def btn_image(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    await _show_image_help(message)
