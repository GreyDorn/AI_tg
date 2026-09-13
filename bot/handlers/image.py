import logging
import re
from aiogram import Router, F
from aiogram.filters import Command, CommandObject, BaseFilter
from aiogram.types import Message, BufferedInputFile, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User
from db.repository import set_waiting_for_image
from llm.image_gen import ImageGenerationError
from core.image import generate_for_user, resolve_image_model, validate_prompt, sync_user_image_model
from bot.keyboards.main import image_models_keyboard, cancel_keyboard, image_share_keyboard
from bot.i18n import all_menu_button_texts, button_filter, format_model_cost_suffix, image_viral_footer, resolve_lang, t

router = Router()
logger = logging.getLogger(__name__)

MENU_BUTTONS = all_menu_button_texts()

_IMAGE_INTENT = re.compile(
    r"^(?:"
    r"нарисуй(?:те)?|нарисовать|"
    r"draw|paint|sketch|"
    r"create (?:an? )?(?:image|picture|photo)|"
    r"generate (?:an? )?(?:image|picture)|"
    r"создай(?:те)? (?:картинку|изображение|фото|рисунок)|"
    r"сгенерируй(?:те)? (?:картинку|изображение|фото)"
    r")\s+(.+)",
    re.IGNORECASE | re.DOTALL,
)


def _extract_image_intent_prompt(text: str) -> str | None:
    match = _IMAGE_INTENT.match(text.strip())
    if not match:
        return None
    return match.group(1).strip()


class WaitingForImageFilter(BaseFilter):
    async def __call__(self, message: Message, db_user: User) -> bool:
        return db_user.waiting_for_image


class ImageIntentFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        text = message.text or ""
        if not text or text.startswith("/") or text in MENU_BUTTONS:
            return False
        return _extract_image_intent_prompt(text) is not None


def _extension_for_mime(mime_type: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
    }.get(mime_type, "png")


async def _set_waiting(
    db_session: AsyncSession,
    db_user: User,
    waiting: bool,
) -> None:
    if db_user.waiting_for_image == waiting:
        return
    await set_waiting_for_image(db_session, db_user.id, waiting)
    db_user.waiting_for_image = waiting


async def _show_image_help(message: Message, db_user: User, waiting: bool = False, lang: str | None = None) -> None:
    lang = lang or resolve_lang(db_user)
    model_key, model_cfg = resolve_image_model(db_user)
    cost_suffix = format_model_cost_suffix(model_cfg.cost_per_image, lang)

    if waiting:
        text = t("image_help_waiting", lang, model=model_cfg.name, cost_suffix=cost_suffix)
    else:
        text = t("image_help", lang, model=model_cfg.name, cost_suffix=cost_suffix)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=cancel_keyboard(lang) if waiting else image_models_keyboard(model_key, lang),
    )


async def _generate_and_send(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    prompt: str,
) -> None:
    lang = resolve_lang(db_user)
    model_key, model_cfg = resolve_image_model(db_user)

    if not validate_prompt(prompt):
        await message.answer(t("image_prompt_too_long", lang))
        return

    if model_cfg.cost_per_image > 0 and db_user.credits < model_cfg.cost_per_image and not db_user.has_unlimited_access:
        await message.answer(
            t(
                "image_not_enough",
                lang,
                model=model_cfg.name,
                cost=model_cfg.cost_per_image,
                credits=db_user.credits,
            ),
            parse_mode="HTML",
            reply_markup=image_models_keyboard(model_key, lang),
        )
        return

    await sync_user_image_model(db_session, db_user)

    status = await message.answer(
        t("image_drawing", lang, model=model_cfg.name),
        parse_mode="HTML",
    )
    await message.bot.send_chat_action(message.chat.id, "upload_photo")

    try:
        result = await generate_for_user(db_session, db_user, prompt)
    except ImageGenerationError as exc:
        logger.error("Image generation failed user=%s model=%s: %s", db_user.id, model_key, exc)
        if str(exc) == "INSUFFICIENT_CREDITS":
            await status.edit_text(
                t(
                    "image_not_enough",
                    lang,
                    model=model_cfg.name,
                    cost=model_cfg.cost_per_image,
                    credits=db_user.credits,
                ),
                parse_mode="HTML",
                reply_markup=image_models_keyboard(model_key, lang),
            )
            return
        if str(exc) == "SPEND_FAILED":
            await status.edit_text(t("image_spend_failed", lang))
            return
        error_text = str(exc)
        if "429" in error_text or "quota" in error_text.lower() or "rate" in error_text.lower():
            user_message = t("image_busy", lang)
        elif "402" in error_text or "insufficient" in error_text.lower() or "credits" in error_text.lower():
            user_message = t("image_model_unavailable", lang, model=model_cfg.name)
        elif "text instead of image" in error_text.lower():
            user_message = t("image_text_instead", lang)
        else:
            user_message = t("image_failed", lang)
        await status.edit_text(user_message, parse_mode="HTML", reply_markup=image_models_keyboard(model_key, lang))
        return
    except Exception:
        logger.exception("Unexpected image generation error user=%s model=%s", db_user.id, model_key)
        await status.edit_text(t("image_failed_later", lang))
        return

    ext = _extension_for_mime(result.mime_type)
    bot_info = await message.bot.get_me()
    viral = image_viral_footer(bot_info.username, lang)
    caption = f"🎨 {result.model_name}\n{prompt[:800]}{viral}"

    try:
        await status.delete()
    except Exception:
        pass

    try:
        await message.answer_photo(
            BufferedInputFile(result.image_bytes, filename=f"image.{ext}"),
            caption=caption,
            reply_markup=image_share_keyboard(bot_info.username, db_user.id, lang),
        )
    except Exception:
        logger.exception("Failed to send photo user=%s model=%s", db_user.id, model_key)
        await message.answer(t("image_send_failed", lang))
        return

    await _set_waiting(db_session, db_user, True)


@router.callback_query(F.data == "cancel")
async def cancel_image_prompt(
    callback: CallbackQuery,
    db_session: AsyncSession,
    db_user: User,
    lang: str = "en",
) -> None:
    if not db_user.waiting_for_image:
        await callback.answer(t("image_cancel_nothing", lang))
        return
    await _set_waiting(db_session, db_user, False)
    await callback.message.edit_text(t("image_cancelled", lang))
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
        await _set_waiting(db_session, db_user, True)
        await _show_image_help(message, db_user, waiting=True)
        return
    await _generate_and_send(message, db_session, db_user, prompt)


@router.message(button_filter("create_image"))
async def btn_image(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    lang: str = "en",
) -> None:
    await _set_waiting(db_session, db_user, True)
    await _show_image_help(message, db_user, waiting=True, lang=lang)


@router.message(F.text, ImageIntentFilter())
async def image_intent_message(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    prompt = _extract_image_intent_prompt(message.text or "")
    if not prompt:
        return
    await _generate_and_send(message, db_session, db_user, prompt)


@router.message(F.text & ~F.text.startswith("/") & ~F.text.in_(MENU_BUTTONS), WaitingForImageFilter())
async def image_prompt_followup(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
) -> None:
    await _generate_and_send(message, db_session, db_user, message.text.strip())
