import logging
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession
from config import (
    MONETIZATION_ENABLED,
    FREE_CREDITS_ON_START,
    DAILY_FREE_CREDITS,
    REFERRAL_BONUS_CREDITS,
    SUBSCRIPTION_PRICE_STARS,
    IMAGE_MODELS,
    MUSIC_MODELS,
    MODELS,
)
from llm.music_gen import is_music_feature_enabled
from db.models import User
from db.repository import (
    create_conversation,
    clear_waiting_modes,
    count_referrals,
    apply_referral_milestones,
    get_user,
)
from bot.keyboards.main import main_menu, growth_keyboard
from bot.i18n import t, button_filter, format_model_cost_suffix, milestone_label, resolve_lang
from bot.utils.growth import (
    referral_link,
    invite_dashboard_text,
    new_referrer_notification_text,
    milestone_unlocked_text,
)

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    is_new_user: bool = False,
    lang: str = "en",
) -> None:
    bot_info = await message.bot.get_me()
    music_line = ""
    if is_music_feature_enabled():
        music_line = t("start_music_line", lang)

    if MONETIZATION_ENABLED:
        ref_line = t("start_ref_line", lang, bonus=REFERRAL_BONUS_CREDITS)
        welcome_extra = ""
        if is_new_user and db_user.referred_by:
            welcome_extra = t("start_referred", lang, credits=FREE_CREDITS_ON_START)
        welcome_key = "start_welcome"
        welcome_kwargs = dict(
            name=message.from_user.first_name,
            free_start=FREE_CREDITS_ON_START,
            daily=DAILY_FREE_CREDITS,
            welcome_extra=welcome_extra,
            music_line=music_line,
            ref_line=ref_line,
        )
    else:
        welcome_key = "start_welcome_free"
        welcome_kwargs = dict(
            name=message.from_user.first_name,
            music_line=music_line,
        )

    await message.answer(
        t(welcome_key, lang, **welcome_kwargs),
        parse_mode="HTML",
        reply_markup=main_menu(lang),
    )

    if MONETIZATION_ENABLED and is_new_user:
        ref_link = referral_link(bot_info.username, db_user.id)
        await message.answer(
            invite_dashboard_text(ref_link, 0, db_user.credits, 0, lang),
            parse_mode="HTML",
            reply_markup=growth_keyboard(bot_info.username, db_user.id, lang),
        )

        if db_user.referred_by:
            await _notify_referrer(
                message, db_session, db_user.referred_by, message.from_user.first_name,
            )

    await create_conversation(db_session, db_user.id, db_user.current_model)


async def _notify_referrer(
    message: Message,
    db_session: AsyncSession,
    referrer_id: int,
    friend_name: str,
) -> None:
    try:
        rewards = await apply_referral_milestones(db_session, referrer_id)
        referrer = await get_user(db_session, referrer_id)
        if not referrer:
            return
        await db_session.refresh(referrer)
        ref_count = await count_referrals(db_session, referrer_id)
        referrer_lang = resolve_lang(referrer)
        await message.bot.send_message(
            referrer_id,
            new_referrer_notification_text(friend_name, ref_count, referrer.credits, referrer_lang),
            parse_mode="HTML",
            reply_markup=growth_keyboard(
                (await message.bot.get_me()).username, referrer_id, referrer_lang,
            ),
        )
        if rewards:
            localized = [milestone_label(r, referrer_lang) for r in rewards]
            await message.bot.send_message(
                referrer_id,
                milestone_unlocked_text(localized, referrer_lang),
                parse_mode="HTML",
            )
    except TelegramForbiddenError:
        logger.info("Referrer %s blocked the bot — skip notification", referrer_id)
    except Exception:
        logger.exception("Failed to notify referrer %s", referrer_id)


@router.message(Command("help"))
async def cmd_help(message: Message, lang: str = "en") -> None:
    models_text = "\n".join(
        f"• <b>{m.name}</b> — {m.description}"
        for m in MODELS.values()
    )
    image_models_text = "\n".join(
        f"• <b>{m.name}</b> — {m.description}{format_model_cost_suffix(m.cost_per_image, lang)}"
        for m in IMAGE_MODELS.values()
    )
    music_section = ""
    music_commands = ""
    if is_music_feature_enabled():
        music_models_text = "\n".join(
            f"• <b>{m.name}</b> — {m.description}"
            f"{format_model_cost_suffix(m.cost_per_track, lang)}, ~{m.duration_seconds}s"
            for m in MUSIC_MODELS.values()
        )
        music_commands = t("help_music_commands", lang)
        music_section = t("help_music_section", lang, models=music_models_text)

    if MONETIZATION_ENABLED:
        help_key = "help"
        help_kwargs = dict(
            music_commands=music_commands,
            models_text=models_text,
            image_models_text=image_models_text,
            music_section=music_section,
            free_start=FREE_CREDITS_ON_START,
            daily=DAILY_FREE_CREDITS,
            bonus=REFERRAL_BONUS_CREDITS,
            price=SUBSCRIPTION_PRICE_STARS,
        )
    else:
        help_key = "help_free"
        help_kwargs = dict(
            music_commands=music_commands,
            models_text=models_text,
            image_models_text=image_models_text,
            music_section=music_section,
        )

    await message.answer(
        t(help_key, lang, **help_kwargs),
        parse_mode="HTML",
    )


@router.message(Command("newchat"))
@router.message(button_filter("new_chat"))
async def cmd_newchat(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    lang: str = "en",
) -> None:
    await clear_waiting_modes(db_session, db_user.id)
    db_user.waiting_for_image = False
    db_user.waiting_for_music = False
    await create_conversation(db_session, db_user.id, db_user.current_model)
    await message.answer(
        t("newchat_done", lang, model=MODELS[db_user.current_model].name),
        parse_mode="HTML",
    )
