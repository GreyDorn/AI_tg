"""Image generation flow for MAX bot."""

from __future__ import annotations

import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from config import DEFAULT_IMAGE_MODEL, IMAGE_MODELS
from db.models import User
from db.repository import set_waiting_for_image, update_user_image_model, spend_credits_idempotent
from core.image import validate_prompt
from core.credits import can_afford
from max_bot.keyboards import available_image_models
from max_bot.api import upload_image_bytes, send_image_message, send_message
from max_bot.gateway_client import GatewayError, generate_image as generate_via_gateway
from max_bot.keyboards import image_models_keyboard, cancel_image_keyboard, main_menu_keyboard

logger = logging.getLogger(__name__)

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


def extract_image_intent_prompt(text: str) -> str | None:
    match = _IMAGE_INTENT.match(text.strip())
    if not match:
        return None
    return match.group(1).strip()


def _extension_for_mime(mime_type: str) -> str:
    return {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime_type, "png")


def resolve_max_image_model_key(current: str) -> str:
    available = available_image_models()
    if current in available:
        return current
    if DEFAULT_IMAGE_MODEL in available:
        return DEFAULT_IMAGE_MODEL
    return next(iter(available))


async def ensure_free_image_model(session: AsyncSession, user: User) -> tuple[str, object]:
    model_key = resolve_max_image_model_key(user.current_image_model)
    if model_key != user.current_image_model:
        await update_user_image_model(session, user.id, model_key)
        user.current_image_model = model_key
    return model_key, IMAGE_MODELS[model_key]


async def set_image_waiting(session: AsyncSession, user: User, waiting: bool) -> None:
    if user.waiting_for_image == waiting:
        return
    await set_waiting_for_image(session, user.id, waiting)
    user.waiting_for_image = waiting


def image_models_text(current_key: str) -> str:
    model = IMAGE_MODELS[current_key]
    return (
        f"Выберите модель для генерации картинок.\n"
        f"Текущая: {model.name}\n\n"
        f"После выбора опишите, что нарисовать."
    )


async def show_image_models(user_id: int, current_key: str) -> None:
    await send_message(
        user_id=user_id,
        text=image_models_text(current_key),
        attachments=image_models_keyboard(current_key),
    )


async def generate_and_send(
    user_id: int,
    session: AsyncSession,
    user: User,
    prompt: str,
    *,
    operation_key: str | None = None,
) -> None:
    model_key, model_cfg = await ensure_free_image_model(session, user)

    if not validate_prompt(prompt):
        await send_message(
            user_id=user_id,
            text="Описание слишком длинное (макс. 1000 символов).",
            attachments=image_models_keyboard(model_key),
        )
        return

    cost = model_cfg.cost_per_image
    if cost > 0 and not can_afford(user, cost):
        await send_message(
            user_id=user_id,
            text=f"Недостаточно запросов для {model_cfg.name} (нужно {cost}).",
            attachments=image_models_keyboard(model_key),
        )
        return

    await send_message(
        user_id=user_id,
        text=f"🎨 Рисую… ({model_cfg.name})",
        attachments=cancel_image_keyboard(),
    )

    try:
        image_bytes, mime_type, _, model_name = await generate_via_gateway(model_key, prompt)
    except GatewayError as exc:
        logger.error("Image generation failed user=%s: %s", user.id, exc)
        low = str(exc).lower()
        if "429" in low or "rate" in low or "quota" in low:
            msg = "⏳ Сервис генерации занят. Попробуйте через минуту."
        elif "402" in low or "insufficient" in low or "credits" in low:
            msg = f"⚠️ Модель {model_cfg.name} сейчас недоступна. Выберите другую."
        else:
            msg = "❌ Не удалось создать картинку. Попробуйте другую модель или короче опишите."
        await send_message(user_id=user_id, text=msg, attachments=image_models_keyboard(model_key))
        return
    except Exception:
        logger.exception("Image generation failed user=%s", user.id)
        await send_message(user_id=user_id, text="❌ Ошибка генерации. Попробуйте позже.")
        return

    if cost > 0 and not user.has_unlimited_access:
        spent = await spend_credits_idempotent(session, user.id, cost, operation_key)
        if not spent:
            await send_message(user_id=user_id, text="Не удалось списать запросы.")
            return

    ext = _extension_for_mime(mime_type)
    caption = f"🎨 {model_name}\n{prompt[:800]}"

    try:
        image_payload = await upload_image_bytes(image_bytes, filename=f"image.{ext}", mime_type=mime_type)
    except Exception:
        logger.exception("MAX image upload failed user=%s", user.id)
        await send_message(user_id=user_id, text="❌ Картинка создана, но не отправилась. Попробуйте ещё раз.")
        return

    ok = await send_image_message(
        user_id=user_id,
        text=caption,
        image_payload=image_payload,
        extra_attachments=main_menu_keyboard(),
    )
    if not ok:
        await send_message(user_id=user_id, text="❌ Не удалось отправить картинку в MAX.")
        return

    await set_image_waiting(session, user, True)


async def select_image_model(
    user_id: int,
    session: AsyncSession,
    user: User,
    model_key: str,
) -> None:
    available = available_image_models()
    if model_key not in available:
        await send_message(user_id=user_id, text="Эта модель сейчас недоступна.")
        return

    if model_key != user.current_image_model:
        await update_user_image_model(session, user.id, model_key)
        user.current_image_model = model_key

    await set_image_waiting(session, user, True)
    model_name = IMAGE_MODELS[model_key].name
    await send_message(
        user_id=user_id,
        text=f"Модель: {model_name}\n\nОпишите, что нарисовать:",
        attachments=cancel_image_keyboard(),
    )
