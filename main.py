import sys
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config import BOT_TOKEN, ADMIN_ID
from db.repository import init_db, SessionFactory, grant_unlimited
from llm.music_gen import is_pollinations_music_configured, is_music_feature_enabled
from llm.provider_status import (
    probe_openrouter_paid,
    start_openrouter_probe_loop,
    configure_openrouter_notifications,
)
from bot.middlewares.user import UserMiddleware
from bot.middlewares.ratelimit import RateLimitMiddleware
from bot.middlewares.processing_lock import ProcessingLockMiddleware
from bot.handlers import start, chat, models, balance, admin, payment, image, image_models, music, music_models

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан в .env файле!")

    await init_db()
    logger.info("База данных инициализирована")

    openrouter_ok = await probe_openrouter_paid()
    logger.info("OpenRouter paid models: %s", "available" if openrouter_ok else "hidden")
    logger.info(
        "Pollinations music: %s",
        "enabled" if is_music_feature_enabled() else "hidden (not free yet)",
    )

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    configure_openrouter_notifications(bot, ADMIN_ID)
    start_openrouter_probe_loop()
    dp = Dispatcher()

    # Выдаём безлимит администратору
    async with SessionFactory() as session:
        await grant_unlimited(session, ADMIN_ID)

    # Middleware регистрируется на все update-события
    dp.update.middleware(UserMiddleware())
    dp.update.middleware(RateLimitMiddleware())
    dp.update.middleware(ProcessingLockMiddleware())

    # Роутеры (порядок важен: chat последним, так как он ловит все тексты)
    dp.include_router(start.router)
    dp.include_router(models.router)
    dp.include_router(balance.router)
    dp.include_router(admin.router)
    dp.include_router(payment.router)
    dp.include_router(image_models.router)
    dp.include_router(image.router)
    dp.include_router(music_models.router)
    dp.include_router(music.router)
    dp.include_router(chat.router)

    logger.info("Бот запущен")
    allowed_updates = dp.resolve_used_update_types()
    for required_update in ("pre_checkout_query", "message", "callback_query"):
        if required_update not in allowed_updates:
            allowed_updates.append(required_update)
    await dp.start_polling(bot, allowed_updates=allowed_updates)


if __name__ == "__main__":
    asyncio.run(main())
