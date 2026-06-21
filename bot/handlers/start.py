from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import FREE_CREDITS_ON_START, DAILY_FREE_CREDITS, REFERRAL_BONUS_CREDITS, SUBSCRIPTION_PRICE_STARS, MODELS
from db.models import User
from db.repository import create_conversation
from bot.keyboards.main import main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, db_session: AsyncSession, db_user: User) -> None:
    await message.answer(
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        f"Я AI-ассистент с несколькими языковыми моделями.\n\n"
        f"🎁 <b>Тебе доступно {FREE_CREDITS_ON_START} бесплатных запросов</b> для знакомства!\n"
        f"Каждый день — ещё <b>+{DAILY_FREE_CREDITS} бесплатных запроса</b>.\n\n"
        f"<b>Что умею:</b>\n"
        f"• Отвечать на вопросы\n"
        f"• Писать код и тексты\n"
        f"• Анализировать и объяснять\n"
        f"• Переводить и редактировать\n\n"
        f"Просто напиши мне сообщение 👇",
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
    await message.answer(
        f"<b>📚 Помощь</b>\n\n"
        f"<b>Команды:</b>\n"
        f"/start — главное меню\n"
        f"/newchat — начать новый диалог\n"
        f"/models — выбрать модель\n"
        f"/balance — баланс запросов\n"
        f"/buy — безлимитная подписка\n"
        f"/referral — реферальная программа\n"
        f"/help — эта справка\n\n"
        f"<b>Доступные модели:</b>\n{models_text}\n\n"
        f"<b>Бесплатные запросы:</b>\n"
        f"• {FREE_CREDITS_ON_START} запросов при регистрации\n"
        f"• +{DAILY_FREE_CREDITS} каждый день\n"
        f"• +{REFERRAL_BONUS_CREDITS} за каждого приглашённого друга\n\n"
        f"💎 <b>Безлимитная подписка</b> — {SUBSCRIPTION_PRICE_STARS} ⭐/месяц",
        parse_mode="HTML",
    )


@router.message(Command("newchat"))
@router.message(lambda m: m.text == "💬 Новый чат")
async def cmd_newchat(message: Message, db_session: AsyncSession, db_user: User) -> None:
    conv = await create_conversation(db_session, db_user.id, db_user.current_model)
    await message.answer(
        f"✅ Новый диалог начат!\n"
        f"Модель: <b>{MODELS[db_user.current_model].name}</b>",
        parse_mode="HTML",
    )
