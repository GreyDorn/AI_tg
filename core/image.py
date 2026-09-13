import logging

from sqlalchemy.ext.asyncio import AsyncSession

from config import IMAGE_MODELS
from db.models import User
from db.repository import spend_credits, update_user_image_model
from llm.image_gen import generate_image, ImageGenerationError
from llm.provider_status import resolve_image_model_key
from core.credits import can_afford
from core.types import ImageGenerationResult

logger = logging.getLogger(__name__)

MAX_PROMPT_LEN = 1000


def resolve_image_model(user: User) -> tuple[str, object]:
    model_key = resolve_image_model_key(user.current_image_model)
    return model_key, IMAGE_MODELS[model_key]


async def sync_user_image_model(session: AsyncSession, user: User) -> tuple[str, object]:
    model_key, model_cfg = resolve_image_model(user)
    if model_key != user.current_image_model:
        user.current_image_model = model_key
        await update_user_image_model(session, user.id, model_key)
    return model_key, model_cfg


def validate_prompt(prompt: str) -> bool:
    return len(prompt) <= MAX_PROMPT_LEN


async def generate_for_user(
    session: AsyncSession,
    user: User,
    prompt: str,
) -> ImageGenerationResult:
    model_key, model_cfg = await sync_user_image_model(session, user)
    cost = model_cfg.cost_per_image

    logger.info(
        "Image request user=%s model=%s prompt=%r",
        user.id,
        model_key,
        prompt[:120],
    )

    if cost > 0 and not can_afford(user, cost):
        raise ImageGenerationError("INSUFFICIENT_CREDITS")

    image_bytes, mime_type = await generate_image(prompt, model_key)

    credits_spent = 0
    if cost > 0 and not user.has_unlimited_access:
        spent = await spend_credits(session, user.id, cost)
        if not spent:
            raise ImageGenerationError("SPEND_FAILED")
        credits_spent = cost

    return ImageGenerationResult(
        image_bytes=image_bytes,
        mime_type=mime_type,
        model_key=model_key,
        model_name=model_cfg.name,
        credits_spent=credits_spent,
    )
