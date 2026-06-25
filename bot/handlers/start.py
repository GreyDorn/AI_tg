import logging
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession
from config import FREE_CREDITS_ON_START, DAILY_FREE_CREDITS, REFERRAL_BONUS_CREDITS, SUBSCRIPTION_PRICE_STARS, IMAGE_MODELS, MUSIC_MODELS, MODELS
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
) -> None:
    bot_info = await message.bot.get_me()
    ref_line = (
        f"\n\n👥 Invite friends → <b>+{REFERRAL_BONUS_CREDITS} requests</b> each "
        f"(milestones up to 1 month free) → /invite"
    )
    welcome_extra = ""
    if is_new_user and db_user.referred_by:
        welcome_extra = (
            f"\n\n🎁 You joined via a friend's link — "
            f"<b>{FREE_CREDITS_ON_START} requests</b> are ready to use!"
        )

    music_line = ""
    if is_music_feature_enabled():
        music_line = "\n• Create music with /music 🎵"

    await message.answer(
        f"👋 <b>Hey, {message.from_user.first_name}!</b>\n\n"
        f"I'm a free AI assistant with <b>multiple models</b>:\n"
        f"Llama, Gemini, DeepSeek and more.\n\n"
        f"🎁 <b>{FREE_CREDITS_ON_START} free requests</b> to start\n"
        f"🎁 <b>+{DAILY_FREE_CREDITS}</b> every day{welcome_extra}\n\n"
        f"<b>Try now:</b>\n"
        f"• Send any question in chat 💬\n"
        f"• Send a photo — Gemini will analyze it 📷\n"
        f"• Create images with /image 🎨{music_line}\n"
        f"• Pick a model in 🤖 Models\n"
        f"• Check balance in 💰 Balance{ref_line}",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )

    if is_new_user:
        ref_link = referral_link(bot_info.username, db_user.id)
        await message.answer(
            invite_dashboard_text(ref_link, 0, db_user.credits, 0),
            parse_mode="HTML",
            reply_markup=growth_keyboard(bot_info.username, db_user.id),
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
        await message.bot.send_message(
            referrer_id,
            new_referrer_notification_text(friend_name, ref_count, referrer.credits),
            parse_mode="HTML",
            reply_markup=growth_keyboard(
                (await message.bot.get_me()).username, referrer_id,
            ),
        )
        if rewards:
            await message.bot.send_message(
                referrer_id,
                milestone_unlocked_text(rewards),
                parse_mode="HTML",
            )
    except TelegramForbiddenError:
        logger.info("Referrer %s blocked the bot — skip notification", referrer_id)
    except Exception:
        logger.exception("Failed to notify referrer %s", referrer_id)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    models_text = "\n".join(
        f"• <b>{m.name}</b> — {m.description}"
        for m in MODELS.values()
    )
    image_models_text = "\n".join(
        f"• <b>{m.name}</b> — {m.description}"
        + (f" ({m.cost_per_image} req)" if m.cost_per_image else " (free)")
        for m in IMAGE_MODELS.values()
    )
    music_models_text = ""
    music_commands = ""
    music_section = ""
    if is_music_feature_enabled():
        music_models_text = "\n".join(
            f"• <b>{m.name}</b> — {m.description}"
            + (f" ({m.cost_per_track} req)" if m.cost_per_track else " (free)")
            + f", ~{m.duration_seconds}s"
            for m in MUSIC_MODELS.values()
        )
        music_commands = (
            "/music — create music\n"
            "/musicmodels — choose music model\n"
        )
        music_section = f"<b>Music models:</b>\n{music_models_text}\n\n"
    await message.answer(
        f"<b>📚 Help</b>\n\n"
        f"<b>Commands:</b>\n"
        f"/start — main menu\n"
        f"/newchat — start a new conversation\n"
        f"/models — choose a text model\n"
        f"/image — create an image\n"
        f"/imagemodels — choose image model\n"
        f"{music_commands}"
        f"/balance — your request balance\n"
        f"/buy — unlimited subscription\n"
        f"/referral — referral program\n"
        f"/help — this help message\n\n"
        f"<b>Text models:</b>\n{models_text}\n\n"
        f"<b>Image models:</b>\n{image_models_text}\n\n"
        f"{music_section}"
        f"<b>Free requests:</b>\n"
        f"• {FREE_CREDITS_ON_START} requests on registration\n"
        f"• +{DAILY_FREE_CREDITS} every day\n"
        f"• +{REFERRAL_BONUS_CREDITS} for each referred friend (milestones → free unlimited)\n"
        f"• Leaderboard: /top\n\n"
        f"💎 <b>Unlimited subscription</b> — {SUBSCRIPTION_PRICE_STARS} ⭐ per month",
        parse_mode="HTML",
    )


@router.message(Command("newchat"))
@router.message(lambda m: m.text == "💬 New Chat")
async def cmd_newchat(message: Message, db_session: AsyncSession, db_user: User) -> None:
    await clear_waiting_modes(db_session, db_user.id)
    db_user.waiting_for_image = False
    db_user.waiting_for_music = False
    await create_conversation(db_session, db_user.id, db_user.current_model)
    await message.answer(
        f"✅ <b>New conversation started!</b>\n\n"
        f"Previous chat history was cleared.\n"
        f"Model: <b>{MODELS[db_user.current_model].name}</b>\n\n"
        f"Tip: use /start to see the welcome message again.",
        parse_mode="HTML",
    )
