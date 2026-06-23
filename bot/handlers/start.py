from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import FREE_CREDITS_ON_START, DAILY_FREE_CREDITS, REFERRAL_BONUS_CREDITS, SUBSCRIPTION_PRICE_STARS, IMAGE_MODELS, MUSIC_MODELS, MODELS
from llm.music_gen import is_music_feature_enabled
from db.models import User
from db.repository import create_conversation, set_waiting_for_image, set_waiting_for_music
from bot.keyboards.main import main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, db_session: AsyncSession, db_user: User) -> None:
    features = (
        "• Answer questions\n"
        "• Write code and content\n"
        "• Analyze and explain\n"
        "• Translate and edit\n"
        "• Create images with /image\n"
    )
    if is_music_feature_enabled():
        features += "• Create music with /music\n"
    await message.answer(
        f"👋 <b>Hey, {message.from_user.first_name}!</b>\n\n"
        f"I'm an AI assistant with multiple language models.\n\n"
        f"🎁 <b>You get {FREE_CREDITS_ON_START} free requests</b> to get started!\n"
        f"Every day — another <b>+{DAILY_FREE_CREDITS} free requests</b>.\n\n"
        f"<b>What I can do:</b>\n"
        f"{features}\n"
        f"Just send me a message 👇",
        parse_mode="HTML",
        reply_markup=main_menu(),
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
        f"• +{REFERRAL_BONUS_CREDITS} for each referred friend\n\n"
        f"💎 <b>Unlimited subscription</b> — {SUBSCRIPTION_PRICE_STARS} ⭐ per month",
        parse_mode="HTML",
    )


@router.message(Command("newchat"))
@router.message(lambda m: m.text == "💬 New Chat")
async def cmd_newchat(message: Message, db_session: AsyncSession, db_user: User) -> None:
    await set_waiting_for_image(db_session, db_user.id, False)
    await set_waiting_for_music(db_session, db_user.id, False)
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
