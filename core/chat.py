import logging
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    MODELS,
    MAX_CONTEXT_MESSAGES,
    DEFAULT_VISION_MODEL_KEY,
    DEFAULT_VISION_PROMPT,
    GEMINI_API_KEY,
    resolve_model_key,
)
from db.models import Message, User
from db.repository import (
    get_active_conversation,
    create_conversation,
    add_message,
    get_conversation_messages,
    update_user_model,
)
from llm import get_llm
from llm.gemini import GeminiLLM
from core.credits import can_afford, charge
from core.types import CreditStatus, TextChatSetup, VisionChatSetup

logger = logging.getLogger(__name__)

_vision_llm = GeminiLLM()


def vision_model_for_user(user: User) -> tuple[str, object]:
    current_key = resolve_model_key(user.current_model)
    current_cfg = MODELS[current_key]
    if current_cfg.supports_vision and current_cfg.provider == "google":
        return current_key, current_cfg
    return DEFAULT_VISION_MODEL_KEY, MODELS[DEFAULT_VISION_MODEL_KEY]


def photo_user_content(caption: str | None) -> str:
    caption = (caption or "").strip()
    return f"[📷 Image] {caption}" if caption else "[📷 Image]"


def is_vision_available() -> bool:
    return bool(GEMINI_API_KEY)


async def sync_user_model_key(session: AsyncSession, user: User) -> str:
    model_key = resolve_model_key(user.current_model)
    if model_key != user.current_model:
        await update_user_model(session, user.id, model_key)
        user.current_model = model_key
    return model_key


async def revert_user_model(
    session: AsyncSession,
    user: User,
    previous_model_key: str | None,
) -> None:
    if not previous_model_key or user.current_model == previous_model_key:
        return
    await update_user_model(session, user.id, previous_model_key)
    user.current_model = previous_model_key


async def setup_text_chat(
    session: AsyncSession,
    user: User,
    text: str,
    *,
    operation_key: str | None = None,
) -> TextChatSetup | None:
    """Prepare DB state for a text message. Returns None if credits denied."""
    model_key = await sync_user_model_key(session, user)
    model_cfg = MODELS[model_key]

    if not can_afford(user, model_cfg.cost_per_message):
        return None

    conv = await get_active_conversation(session, user.id)
    if not conv:
        conv = await create_conversation(session, user.id, model_key)

    await add_message(session, conv.id, "user", text)

    all_messages = await get_conversation_messages(session, conv.id)
    context = all_messages[-MAX_CONTEXT_MESSAGES:]
    if len(all_messages) > len(context):
        logger.info(
            "Context window for user %s: using last %d of %d messages",
            user.id,
            len(context),
            len(all_messages),
        )

    credit = await charge(session, user, model_cfg.cost_per_message, operation_key=operation_key)
    if credit.status == CreditStatus.DENIED:
        return None

    return TextChatSetup(
        conv_id=conv.id,
        model_key=model_key,
        model_name=model_cfg.name,
        credits_spent=credit.credits_spent,
        context=context,
    )


def build_text_stream(setup: TextChatSetup) -> AsyncIterator[str]:
    llm, model_id, disable_thinking = get_llm(setup.model_key)
    return llm.stream(setup.context, model_id, disable_thinking)


async def save_assistant_message(session: AsyncSession, conv_id: int, content: str) -> None:
    await add_message(session, conv_id, "assistant", content)


async def setup_vision_chat(
    session: AsyncSession,
    user: User,
    *,
    caption: str | None,
    image_bytes: bytes,
    mime_type: str,
    operation_key: str | None = None,
) -> VisionChatSetup | None:
    """Returns setup or None on credit denial (reverts model switch if needed)."""
    vision_key, vision_cfg = vision_model_for_user(user)
    if not can_afford(user, vision_cfg.cost_per_message):
        return None

    previous_model_key = resolve_model_key(user.current_model)
    auto_switched = previous_model_key != vision_key
    revert_model_key = previous_model_key if auto_switched else None
    if auto_switched:
        await update_user_model(session, user.id, vision_key)
        user.current_model = vision_key

    conv = await get_active_conversation(session, user.id)
    if not conv:
        conv = await create_conversation(session, user.id, user.current_model)

    user_content = photo_user_content(caption)
    await add_message(session, conv.id, "user", user_content)

    all_messages = await get_conversation_messages(session, conv.id)
    context = all_messages[:-1][-MAX_CONTEXT_MESSAGES:]

    credit = await charge(session, user, vision_cfg.cost_per_message, operation_key=operation_key)
    if credit.status == CreditStatus.DENIED:
        await revert_user_model(session, user, revert_model_key)
        return None

    prompt = (caption or "").strip() or DEFAULT_VISION_PROMPT
    logger.info("Photo analysis user=%s prompt=%r size=%d", user.id, prompt[:120], len(image_bytes))

    return VisionChatSetup(
        conv_id=conv.id,
        vision_key=vision_key,
        vision_name=vision_cfg.name,
        credits_spent=credit.credits_spent,
        auto_switched=auto_switched,
        revert_model_key=revert_model_key,
        image_bytes=image_bytes,
        mime_type=mime_type,
        prompt=prompt,
        context=context,
    )


def build_vision_stream(setup: VisionChatSetup) -> AsyncIterator[str]:
    vision_cfg = MODELS[setup.vision_key]
    return _vision_llm.stream_vision(
        setup.image_bytes,
        setup.mime_type,
        setup.prompt,
        setup.context,
        vision_cfg.id,
    )
