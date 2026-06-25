from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import FREE_CREDITS_ON_START, DAILY_FREE_CREDITS, REFERRAL_BONUS_CREDITS, SUBSCRIPTION_PRICE_STARS, IMAGE_MODELS, MODELS
from db.models import User
from db.repository import create_conversation
from bot.keyboards.main import main_menu, growth_keyboard
from bot.utils.growth import referral_link, referral_program_text

router = Router()


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    db_session: AsyncSession,
    db_user: User,
    is_new_user: bool = False,
) -> None:
    bot_info = await message.bot.get_me()
    ref_line = (
        f"\n\n👥 Invite friends → <b>+{REFERRAL_BONUS_CREDITS} requests</b> each via 👥 Referral"
    )
    welcome_extra = ""
    if is_new_user and db_user.referred_by:
        welcome_extra = (
            f"\n\n🎁 You joined via a friend's link — "
            f"<b>{FREE_CREDITS_ON_START} requests</b> are ready to use!"
        )

    await message.answer(
        f"👋 <b>Hey, {message.from_user.first_name}!</b>\n\n"
        f"I'm a free AI assistant with <b>multiple models</b>:\n"
        f"Llama, Gemini, DeepSeek and more.\n\n"
        f"🎁 <b>{FREE_CREDITS_ON_START} free requests</b> to start\n"
        f"🎁 <b>+{DAILY_FREE_CREDITS}</b> every day{welcome_extra}\n\n"
        f"<b>Try now:</b>\n"
        f"• Send any question in chat 💬\n"
        f"• Send a photo — Gemini will analyze it 📷\n"
        f"• Create images with /image 🎨\n"
        f"• Pick a model in 🤖 Models\n"
        f"• Check balance in 💰 Balance{ref_line}",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )

    if is_new_user:
        ref_link = referral_link(bot_info.username, db_user.id)
        await message.answer(
            referral_program_text(ref_link),
            parse_mode="HTML",
            reply_markup=growth_keyboard(bot_info.username, db_user.id),
        )

    await create_conversation(db_session, db_user.id, db_user.current_model)


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
    await message.answer(
        f"<b>📚 Help</b>\n\n"
        f"<b>Commands:</b>\n"
        f"/start — main menu\n"
        f"/newchat — start a new conversation\n"
        f"/models — choose a text model\n"
        f"/image — create an image\n"
        f"/imagemodels — choose image model\n"
        f"/balance — your request balance\n"
        f"/buy — unlimited subscription\n"
        f"/referral — referral program\n"
        f"/help — this help message\n\n"
        f"<b>Text models:</b>\n{models_text}\n\n"
        f"<b>Image models:</b>\n{image_models_text}\n\n"
        f"<b>Free requests:</b>\n"
        f"• {FREE_CREDITS_ON_START} requests on registration\n"
        f"• +{DAILY_FREE_CREDITS} every day\n"
        f"• +{REFERRAL_BONUS_CREDITS} for each referred friend\n\n"
        f"💎 <b>Unlimited subscription</b> — {SUBSCRIPTION_PRICE_STARS} ⭐ per month",
        parse_mode="HTML",
    )


@router.message(Command("newchat"))
@router.message(lambda m: m.text == "💬 New Chat")
async def cmd_newchat(message: Message, db_session: AsyncSession, db_user: User) -> None:
    await create_conversation(db_session, db_user.id, db_user.current_model)
    await message.answer(
        f"✅ <b>New conversation started!</b>\n\n"
        f"Previous chat history was cleared.\n"
        f"Model: <b>{MODELS[db_user.current_model].name}</b>\n\n"
        f"Tip: use /start to see the welcome message again.",
        parse_mode="HTML",
    )
