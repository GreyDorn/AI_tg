"""UI localization: Russian when Telegram language_code starts with 'ru'."""
from __future__ import annotations

from aiogram import F
from aiogram.types import User as TgUser

from db.models import User
from config import MONETIZATION_ENABLED

LANGS = ("en", "ru")
DEFAULT_LANG = "en"


def resolve_lang(user: TgUser | User | None) -> str:
    code = DEFAULT_LANG
    if user is not None:
        code = getattr(user, "language_code", None) or code
    if str(code).lower().startswith("ru"):
        return "ru"
    return "en"


def _pick(lang: str) -> str:
    return lang if lang in LANGS else DEFAULT_LANG


def t(key: str, lang: str, **fmt) -> str:
    text = MESSAGES[key][_pick(lang)]
    return text.format(**fmt) if fmt else text


# ── Menu buttons ──────────────────────────────────────────────────────────────

BUTTONS: dict[str, dict[str, str]] = {
    "new_chat": {"en": "💬 New Chat", "ru": "💬 Новый чат"},
    "models": {"en": "🤖 Models", "ru": "🤖 Модели"},
    "create_image": {"en": "🎨 Create Image", "ru": "🎨 Создать картинку"},
    "image_models": {"en": "🖼 Image Models", "ru": "🖼 Модели картинок"},
    "create_music": {"en": "🎵 Create Music", "ru": "🎵 Создать музыку"},
    "music_models": {"en": "🎵 Music Models", "ru": "🎵 Модели музыки"},
    "balance": {"en": "💰 Balance", "ru": "💰 Баланс"},
    "referral": {"en": "👥 Referral", "ru": "👥 Рефералы"},
    "subscription": {"en": "💎 Subscription", "ru": "💎 Подписка"},
}

_MENU_BUTTON_KEYS = (
    "new_chat", "models", "create_image", "image_models",
    "create_music", "music_models",
)
_MONETIZATION_BUTTON_KEYS = ("balance", "referral", "subscription")

INLINE = {
    "cancel": {"en": "❌ Cancel", "ru": "❌ Отмена"},
    "cancel_music": {"en": "❌ Cancel", "ru": "❌ Отмена"},
    "share_bot": {"en": "📤 Share bot", "ru": "📤 Поделиться"},
    "share_bot_bonus": {"en": "📤 Share bot (+5 req)", "ru": "📤 Поделиться (+5 зап.)"},
    "share_this_bot": {"en": "📤 Share this bot", "ru": "📤 Поделиться ботом"},
    "buy_stars": {"en": "⭐ Buy Stars — from {price}", "ru": "⭐ Купить Stars — от {price}"},
    "subscribe": {"en": "💎 Subscribe — {price} ⭐", "ru": "💎 Подписка — {price} ⭐"},
    "claim_daily": {"en": "🎁 Claim daily bonus", "ru": "🎁 Забрать бонус"},
}


def btn(key: str, lang: str) -> str:
    return BUTTONS[key][_pick(lang)]


def inline(key: str, lang: str, **fmt) -> str:
    text = INLINE[key][_pick(lang)]
    return text.format(**fmt) if fmt else text


def all_menu_button_texts() -> frozenset[str]:
    return frozenset(btn(key, lang) for key in BUTTONS for lang in LANGS)


def button_filter(key: str):
    return F.text.in_(frozenset(btn(key, lang) for lang in LANGS))


def format_cost(cost: int, lang: str) -> str:
    if not MONETIZATION_ENABLED:
        return ""
    if cost == 0:
        return t("cost_free", lang)
    if cost == 1:
        return t("cost_one", lang)
    return t("cost_many", lang, cost=cost)


def format_model_cost_suffix(cost: int, lang: str) -> str:
    """Returns ' (1 request)' or '' when monetization is off."""
    label = format_cost(cost, lang)
    return f" ({label})" if label else ""


def visible_menu_button_keys() -> tuple[str, ...]:
    keys = list(_MENU_BUTTON_KEYS)
    if MONETIZATION_ENABLED:
        keys.extend(_MONETIZATION_BUTTON_KEYS)
    return tuple(keys)


SHARE_TEXT = {
    "en": (
        "🤖 AI in Telegram — ChatGPT, Gemini, DeepSeek, photo analysis & image generation. "
        "Works right here, no install. Try it:"
    ),
    "ru": (
        "🤖 AI в Telegram — ChatGPT, Gemini, DeepSeek, анализ фото и генерация картинок. "
        "Работает прямо здесь. Попробуй:"
    ),
}

IMAGE_SHARE_TEXT = {
    "en": "🎨 I made this with an AI bot in Telegram — try it yourself:",
    "ru": "🎨 Я сделал это в AI-боте в Telegram — попробуй:",
}


def share_text(lang: str) -> str:
    return SHARE_TEXT[_pick(lang)]


def image_share_text(lang: str) -> str:
    return IMAGE_SHARE_TEXT[_pick(lang)]


def image_viral_footer(bot_username: str, lang: str) -> str:
    return t("image_viral_footer", lang, bot_username=bot_username)


MILESTONE_LABELS = {
    "+15 bonus requests": {"en": "+15 bonus requests", "ru": "+15 бонусных запросов"},
    "3 days unlimited": {"en": "3 days unlimited", "ru": "3 дня безлимита"},
    "7 days unlimited": {"en": "7 days unlimited", "ru": "7 дней безлимита"},
    "1 month unlimited": {"en": "1 month unlimited", "ru": "1 месяц безлимита"},
}


def milestone_label(label: str, lang: str) -> str:
    return MILESTONE_LABELS.get(label, {}).get(_pick(lang), label)


# ── User-facing messages ──────────────────────────────────────────────────────

MESSAGES: dict[str, dict[str, str]] = {
    "cost_free": {"en": "free", "ru": "бесплатно"},
    "cost_one": {"en": "1 request", "ru": "1 запрос"},
    "cost_many": {"en": "{cost} requests", "ru": "{cost} запросов"},
    "image_viral_footer": {
        "en": "\n\n✨ AI art → @{bot_username}",
        "ru": "\n\n✨ AI-арт → @{bot_username}",
    },
    "start_welcome_free": {
        "en": (
            "👋 <b>Hey, {name}!</b>\n\n"
            "I'm an AI assistant with <b>multiple models</b>:\n"
            "Llama, Gemini, DeepSeek and more.\n\n"
            "<b>Try now:</b>\n"
            "• Send any question in chat 💬\n"
            "• Send a photo — Gemini will analyze it 📷\n"
            "• Create images with /image 🎨{music_line}\n"
            "• Pick a model in 🤖 Models"
        ),
        "ru": (
            "👋 <b>Привет, {name}!</b>\n\n"
            "Я AI-ассистент с <b>несколькими моделями</b>:\n"
            "Llama, Gemini, DeepSeek и другие.\n\n"
            "<b>Попробуй:</b>\n"
            "• Напиши любой вопрос в чат 💬\n"
            "• Отправь фото — Gemini проанализирует 📷\n"
            "• Создай картинку через /image 🎨{music_line}\n"
            "• Выбери модель в 🤖 Модели"
        ),
    },
    "start_welcome": {
        "en": (
            "👋 <b>Hey, {name}!</b>\n\n"
            "I'm a free AI assistant with <b>multiple models</b>:\n"
            "Llama, Gemini, DeepSeek and more.\n\n"
            "🎁 <b>{free_start} free requests</b> to start\n"
            "🎁 <b>+{daily}</b> every day{welcome_extra}\n\n"
            "<b>Try now:</b>\n"
            "• Send any question in chat 💬\n"
            "• Send a photo — Gemini will analyze it 📷\n"
            "• Create images with /image 🎨{music_line}\n"
            "• Pick a model in 🤖 Models\n"
            "• Check balance in 💰 Balance{ref_line}"
        ),
        "ru": (
            "👋 <b>Привет, {name}!</b>\n\n"
            "Я бесплатный AI-ассистент с <b>несколькими моделями</b>:\n"
            "Llama, Gemini, DeepSeek и другие.\n\n"
            "🎁 <b>{free_start} бесплатных запросов</b> на старт\n"
            "🎁 <b>+{daily}</b> каждый день{welcome_extra}\n\n"
            "<b>Попробуй:</b>\n"
            "• Напиши любой вопрос в чат 💬\n"
            "• Отправь фото — Gemini проанализирует 📷\n"
            "• Создай картинку через /image 🎨{music_line}\n"
            "• Выбери модель в 🤖 Модели\n"
            "• Баланс в 💰 Баланс{ref_line}"
        ),
    },
    "start_ref_line": {
        "en": "\n\n👥 Invite friends → <b>+{bonus} requests</b> each (milestones up to 1 month free) → /invite",
        "ru": "\n\n👥 Пригласи друзей → <b>+{bonus} запросов</b> за каждого (бонусы до месяца безлимита) → /invite",
    },
    "start_referred": {
        "en": "\n\n🎁 You joined via a friend's link — <b>{credits} requests</b> are ready to use!",
        "ru": "\n\n🎁 Ты перешёл по ссылке друга — <b>{credits} запросов</b> уже на балансе!",
    },
    "start_music_line": {
        "en": "\n• Create music with /music 🎵",
        "ru": "\n• Создай музыку через /music 🎵",
    },
    "newchat_done": {
        "en": (
            "✅ <b>New conversation started!</b>\n\n"
            "Previous chat history was cleared.\n"
            "Model: <b>{model}</b>\n\n"
            "Tip: use /start to see the welcome message again."
        ),
        "ru": (
            "✅ <b>Новый диалог начат!</b>\n\n"
            "История предыдущего чата очищена.\n"
            "Модель: <b>{model}</b>\n\n"
            "Подсказка: /start — снова показать приветствие."
        ),
    },
    "balance_unlimited_perm": {
        "en": "✨ <b>Unlimited access</b> (permanent)",
        "ru": "✨ <b>Безлимитный доступ</b> (навсегда)",
    },
    "balance_unlimited_sub": {
        "en": "✨ <b>Subscription active</b> until <b>{date}</b>",
        "ru": "✨ <b>Подписка активна</b> до <b>{date}</b>",
    },
    "balance_unlimited_body": {
        "en": (
            "💰 <b>Your Balance</b>\n\n"
            "{status}\n\n"
            "Requests: <b>unlimited</b>\n\n"
            "👥 Invite friends — still earn <b>+{bonus}</b> per signup"
        ),
        "ru": (
            "💰 <b>Твой баланс</b>\n\n"
            "{status}\n\n"
            "Запросы: <b>безлимит</b>\n\n"
            "👥 Приглашай друзей — <b>+{bonus}</b> за каждого"
        ),
    },
    "balance_free": {
        "en": (
            "💰 <b>Your Balance</b>\n\n"
            "Requests: <b>{credits}</b>{daily_line}{streak_line}\n\n"
            "<b>Free ways to get more:</b>\n"
            "• Daily login — /balance\n"
            "• Invite friends — /invite (+{bonus} each)\n"
            "• Milestones up to <b>1 month free unlimited</b>\n\n"
            "💎 Unlimited: <b>{price} ⭐/month</b>\n"
            "Tap <b>⭐ Buy Stars</b> then <b>💎 Subscribe</b>"
        ),
        "ru": (
            "💰 <b>Твой баланс</b>\n\n"
            "Запросы: <b>{credits}</b>{daily_line}{streak_line}\n\n"
            "<b>Бесплатно получить ещё:</b>\n"
            "• Заходи каждый день — /balance\n"
            "• Приглашай друзей — /invite (+{bonus} за каждого)\n"
            "• Бонусы до <b>1 месяца безлимита</b>\n\n"
            "💎 Безлимит: <b>{price} ⭐/мес</b>\n"
            "Нажми <b>⭐ Купить Stars</b>, затем <b>💎 Подписка</b>"
        ),
    },
    "balance_daily_added": {
        "en": "\n✅ <b>+{daily}{bonus_part} daily requests added!</b>",
        "ru": "\n✅ <b>+{daily}{bonus_part} ежедневных запросов начислено!</b>",
    },
    "balance_streak": {
        "en": "\n🔥 Streak: <b>{days} days</b> — open daily for bonus requests",
        "ru": "\n🔥 Серия: <b>{days} дн.</b> — заходи каждый день за бонусом",
    },
    "claim_already_unlimited": {
        "en": "You already have unlimited access ✨",
        "ru": "У тебя уже безлимит ✨",
    },
    "claim_already_today": {
        "en": "Already claimed today — come back tomorrow!",
        "ru": "Уже забрал сегодня — возвращайся завтра!",
    },
    "claim_added": {
        "en": "+{daily}{bonus_part} added!",
        "ru": "+{daily}{bonus_part} начислено!",
    },
    "out_of_credits": {
        "en": (
            "❌ <b>Out of requests</b>\n\n"
            "You have: <b>{credits}</b>\n\n"
            "<b>Get more for free:</b>\n"
            "• Tomorrow — <b>+{daily}</b> daily (+ streak bonus 🔥)\n"
            "• Invite a friend — <b>+{bonus}</b> via /invite 👥\n"
            "• 10 friends → <b>3 days unlimited</b> free\n\n"
            "<b>Or unlimited access:</b>\n"
            "1. Tap <b>⭐ Buy Stars</b> (opens inline)\n"
            "2. Tap <b>💎 Subscribe</b> — <b>{price} ⭐/month</b>"
        ),
        "ru": (
            "❌ <b>Запросы закончились</b>\n\n"
            "На балансе: <b>{credits}</b>\n\n"
            "<b>Бесплатно:</b>\n"
            "• Завтра — <b>+{daily}</b> ежедневно (+ бонус за серию 🔥)\n"
            "• Пригласи друга — <b>+{bonus}</b> через /invite 👥\n"
            "• 10 друзей → <b>3 дня безлимита</b>\n\n"
            "<b>Или безлимит:</b>\n"
            "1. Нажми <b>⭐ Купить Stars</b>\n"
            "2. Нажми <b>💎 Подписка</b> — <b>{price} ⭐/мес</b>"
        ),
    },
    "low_credits": {
        "en": (
            "⚠️ <b>{credits} {word} left</b>\n\n"
            "Invite friends → /invite (+{bonus} each, milestones up to 1 month free)\n"
            "Or unlimited → 💎 <b>Subscription</b>"
        ),
        "ru": (
            "⚠️ <b>Осталось {credits} {word}</b>\n\n"
            "Пригласи друзей → /invite (+{bonus} за каждого, бонусы до месяца безлимита)\n"
            "Или безлимит → 💎 <b>Подписка</b>"
        ),
    },
    "request_word_one": {"en": "request", "ru": "запрос"},
    "request_word_many": {"en": "requests", "ru": "запросов"},
    "invite_dashboard": {
        "en": (
            "👥 <b>Invite & Earn</b>\n\n"
            "Your friends invited: <b>{count}</b>\n"
            "Balance: <b>{credits}</b> requests{streak_line}\n\n"
            "<b>Per friend who joins:</b>\n"
            "• You get <b>+{bonus} requests</b>\n"
            "• They get <b>{free_start} requests</b> free\n\n"
            "{milestones}\n\n"
            "🔗 <b>Your link:</b>\n<code>{link}</code>\n\n"
            "Tap <b>Share bot</b> — send to groups, friends, channels 👇"
        ),
        "ru": (
            "👥 <b>Приглашай и зарабатывай</b>\n\n"
            "Друзей приглашено: <b>{count}</b>\n"
            "Баланс: <b>{credits}</b> запросов{streak_line}\n\n"
            "<b>За каждого друга:</b>\n"
            "• Тебе <b>+{bonus} запросов</b>\n"
            "• Ему <b>{free_start} запросов</b> бесплатно\n\n"
            "{milestones}\n\n"
            "🔗 <b>Твоя ссылка:</b>\n<code>{link}</code>\n\n"
            "Нажми <b>Поделиться</b> — отправь друзьям или в чаты 👇"
        ),
    },
    "invite_streak": {
        "en": "\n🔥 Login streak: <b>{days} days</b>",
        "ru": "\n🔥 Серия входов: <b>{days} дн.</b>",
    },
    "invite_streak_bonus": {
        "en": " (+{bonus} extra daily bonus)",
        "ru": " (+{bonus} к ежедневному бонусу)",
    },
    "milestone_header": {
        "en": "<b>🏆 Referral rewards:</b>",
        "ru": "<b>🏆 Награды за друзей:</b>",
    },
    "milestone_row": {
        "en": "{mark} {needed} friends → <b>{label}</b>",
        "ru": "{mark} {needed} друзей → <b>{label}</b>",
    },
    "milestone_next": {
        "en": "\n<b>Next:</b> invite <b>{left}</b> more → {label}",
        "ru": "\n<b>Дальше:</b> ещё <b>{left}</b> → {label}",
    },
    "milestone_all_done": {
        "en": "\n🎉 <b>All milestones unlocked!</b> Keep sharing.",
        "ru": "\n🎉 <b>Все награды получены!</b> Продолжай делиться.",
    },
    "leaderboard_empty": {
        "en": "🏆 <b>Top inviters</b>\n\nNo referrals yet — be the first!\nShare your link: /invite",
        "ru": "🏆 <b>Топ приглашающих</b>\n\nПока никого — будь первым!\nТвоя ссылка: /invite",
    },
    "leaderboard_title": {
        "en": "🏆 <b>Top inviters — this month</b>\n",
        "ru": "🏆 <b>Топ приглашающих — этот месяц</b>\n",
    },
    "leaderboard_row": {
        "en": "{medal} {name} — <b>{count}</b> friends",
        "ru": "{medal} {name} — <b>{count}</b> друзей",
    },
    "leaderboard_footer": {
        "en": "\nWant to climb the board? → /invite\nTop inviters unlock <b>free unlimited</b> access 🎁",
        "ru": "\nХочешь в топ? → /invite\nЛучшие получают <b>бесплатный безлимит</b> 🎁",
    },
    "new_referrer": {
        "en": (
            "🎉 <b>{name}</b> joined via your link!\n\n"
            "+<b>{bonus} requests</b> added\n"
            "Total friends: <b>{count}</b>\n"
            "Balance: <b>{credits}</b>\n\n"
            "Keep sharing → /invite"
        ),
        "ru": (
            "🎉 <b>{name}</b> перешёл по твоей ссылке!\n\n"
            "+<b>{bonus} запросов</b> на баланс\n"
            "Всего друзей: <b>{count}</b>\n"
            "Баланс: <b>{credits}</b>\n\n"
            "Делись дальше → /invite"
        ),
    },
    "milestone_unlocked": {
        "en": "🏆 <b>Referral milestone unlocked!</b>\n\n{items}",
        "ru": "🏆 <b>Награда за друзей получена!</b>\n\n{items}",
    },
    "buy_info": {
        "en": (
            "💎 <b>Unlimited Subscription</b>\n\n"
            "<b>What's included:</b>\n"
            "• Unlimited text requests to <b>all LLM models</b>\n"
            "• Unlimited image generation with <b>all image models</b>\n"
            "  (Gemini Image, Flux Klein, Flux, Turbo)\n"
            "• {days} days of access{sub_status}\n\n"
            "<b>Fair-use limit:</b>\n"
            "• Up to <b>{rate_limit} messages per {rate_window} sec.</b> "
            "(anti-spam protection for everyone)\n\n"
            "Price: <b>{price} ⭐ Stars per month</b>\n\n"
            "ℹ️ Need stars? Tap <b>Buy Stars</b> below — the purchase window "
            "opens right here (via PremiumBot), without leaving the chat.\n"
            "Then tap <b>Subscribe</b> to activate unlimited access."
        ),
        "ru": (
            "💎 <b>Безлимитная подписка</b>\n\n"
            "<b>Что входит:</b>\n"
            "• Безлимитные текстовые запросы ко <b>всем LLM-моделям</b>\n"
            "• Безлимитная генерация картинок <b>всеми моделями</b>\n"
            "  (Gemini Image, Flux Klein, Flux, Turbo)\n"
            "• {days} дней доступа{sub_status}\n\n"
            "<b>Лимит fair-use:</b>\n"
            "• До <b>{rate_limit} сообщений за {rate_window} сек.</b> "
            "(защита от спама)\n\n"
            "Цена: <b>{price} ⭐ Stars в месяц</b>\n\n"
            "ℹ️ Нужны Stars? Нажми <b>Купить Stars</b> — окно покупки "
            "откроется здесь (PremiumBot), без выхода из чата.\n"
            "Затем нажми <b>Подписка</b> для активации."
        ),
    },
    "buy_sub_active": {
        "en": (
            "\n\n✨ <b>Your subscription is active</b> until "
            "<b>{date}</b>\n"
            "A new payment will extend it by {days} more days."
        ),
        "ru": (
            "\n\n✨ <b>Подписка активна</b> до "
            "<b>{date}</b>\n"
            "Новый платёж продлит ещё на {days} дней."
        ),
    },
    "sub_activated": {
        "en": (
            "✅ <b>Subscription activated!</b>\n\n"
            "Unlimited access to all text and image models until "
            "<b>{date}</b> 🎉"
        ),
        "ru": (
            "✅ <b>Подписка активирована!</b>\n\n"
            "Безлимит ко всем текстовым и графическим моделям до "
            "<b>{date}</b> 🎉"
        ),
    },
    "sub_already_paid": {
        "en": "✅ <b>Payment already processed</b>\n\nYour subscription is active until <b>{date}</b>.",
        "ru": "✅ <b>Платёж уже обработан</b>\n\nПодписка активна до <b>{date}</b>.",
    },
    "models_choose": {
        "en": (
            "🤖 <b>Choose a Model</b>\n\n"
            "Current: <b>{current}</b>\n\n"
            "1 request per message for all models.\n"
            "📷 — can read photos in chat (Gemini)"
        ),
        "ru": (
            "🤖 <b>Выбери модель</b>\n\n"
            "Сейчас: <b>{current}</b>\n\n"
            "1 запрос за сообщение для всех моделей.\n"
            "📷 — читает фото в чате (Gemini)"
        ),
    },
    "models_choose_free": {
        "en": (
            "🤖 <b>Choose a Model</b>\n\n"
            "Current: <b>{current}</b>\n\n"
            "📷 — can read photos in chat (Gemini)"
        ),
        "ru": (
            "🤖 <b>Выбери модель</b>\n\n"
            "Сейчас: <b>{current}</b>\n\n"
            "📷 — читает фото в чате (Gemini)"
        ),
    },
    "model_unknown": {"en": "Unknown model.", "ru": "Неизвестная модель."},
    "model_already": {"en": "This model is already selected ✅", "ru": "Эта модель уже выбрана ✅"},
    "model_switched": {"en": "✅ Switched to {name}", "ru": "✅ Переключено на {name}"},
    "reminder_text": {
        "en": (
            "🎁 <b>Your daily bonus is ready!</b>\n\n"
            "Tap below to get <b>+{daily} free requests</b>{streak_hint}\n\n"
            "Or invite friends → <b>+{bonus}</b> each via /invite"
        ),
        "ru": (
            "🎁 <b>Ежедневный бонус готов!</b>\n\n"
            "Нажми ниже, чтобы получить <b>+{daily} запросов</b>{streak_hint}\n\n"
            "Или пригласи друзей → <b>+{bonus}</b> за каждого через /invite"
        ),
    },
    "reminder_streak_active": {
        "en": "\n🔥 Streak: <b>{days} days</b> — don't break it!",
        "ru": "\n🔥 Серия: <b>{days} дн.</b> — не прерывай!",
    },
    "reminder_streak_start": {
        "en": "\n🔥 Come back tomorrow to start a streak!",
        "ru": "\n🔥 Заходи завтра — начни серию!",
    },
    # help
    "help": {
        "en": (
            "<b>📚 Help</b>\n\n"
            "<b>Commands:</b>\n"
            "/start — main menu\n"
            "/newchat — start a new conversation\n"
            "/models — choose a text model\n"
            "/image — create an image\n"
            "/imagemodels — choose image model\n"
            "{music_commands}"
            "/balance — your request balance\n"
            "/buy — unlimited subscription\n"
            "/referral — referral program\n"
            "/invite — invite dashboard\n"
            "/top — referral leaderboard\n"
            "/help — this help message\n\n"
            "<b>Text models:</b>\n{models_text}\n\n"
            "<b>Image models:</b>\n{image_models_text}\n\n"
            "{music_section}"
            "<b>Free requests:</b>\n"
            "• {free_start} requests on registration\n"
            "• +{daily} every day\n"
            "• +{bonus} for each referred friend (milestones → free unlimited)\n"
            "• Leaderboard: /top\n\n"
            "💎 <b>Unlimited subscription</b> — {price} ⭐ per month"
        ),
        "ru": (
            "<b>📚 Справка</b>\n\n"
            "<b>Команды:</b>\n"
            "/start — главное меню\n"
            "/newchat — новый диалог\n"
            "/models — выбор текстовой модели\n"
            "/image — создать картинку\n"
            "/imagemodels — модели для картинок\n"
            "{music_commands}"
            "/balance — баланс запросов\n"
            "/buy — безлимитная подписка\n"
            "/referral — реферальная программа\n"
            "/invite — панель приглашений\n"
            "/top — топ приглашающих\n"
            "/help — эта справка\n\n"
            "<b>Текстовые модели:</b>\n{models_text}\n\n"
            "<b>Модели картинок:</b>\n{image_models_text}\n\n"
            "{music_section}"
            "<b>Бесплатные запросы:</b>\n"
            "• {free_start} при регистрации\n"
            "• +{daily} каждый день\n"
            "• +{bonus} за каждого друга (бонусы → безлимит)\n"
            "• Топ: /top\n\n"
            "💎 <b>Безлимитная подписка</b> — {price} ⭐ в месяц"
        ),
    },
    "help_free": {
        "en": (
            "<b>📚 Help</b>\n\n"
            "<b>Commands:</b>\n"
            "/start — main menu\n"
            "/newchat — start a new conversation\n"
            "/models — choose a text model\n"
            "/image — create an image\n"
            "/imagemodels — choose image model\n"
            "{music_commands}"
            "/help — this help message\n\n"
            "<b>Text models:</b>\n{models_text}\n\n"
            "<b>Image models:</b>\n{image_models_text}\n\n"
            "{music_section}"
        ),
        "ru": (
            "<b>📚 Справка</b>\n\n"
            "<b>Команды:</b>\n"
            "/start — главное меню\n"
            "/newchat — новый диалог\n"
            "/models — выбор текстовой модели\n"
            "/image — создать картинку\n"
            "/imagemodels — модели для картинок\n"
            "{music_commands}"
            "/help — эта справка\n\n"
            "<b>Текстовые модели:</b>\n{models_text}\n\n"
            "<b>Модели картинок:</b>\n{image_models_text}\n\n"
            "{music_section}"
        ),
    },
    "help_music_commands": {
        "en": "/music — create music\n/musicmodels — choose music model\n",
        "ru": "/music — создать музыку\n/musicmodels — модели музыки\n",
    },
    "help_music_section": {
        "en": "<b>Music models:</b>\n{models}\n\n",
        "ru": "<b>Модели музыки:</b>\n{models}\n\n",
    },
    "help_model_free": {
        "en": " ({cost})",
        "ru": " ({cost})",
    },
    # chat
    "chat_thinking": {"en": "⏳", "ru": "⏳"},
    "chat_empty_response": {
        "en": "⚠️ The model returned an empty response.",
        "ru": "⚠️ Модель вернула пустой ответ.",
    },
    "chat_vision_unavailable": {
        "en": "📷 <b>Photo analysis is not available</b>\n\nGemini API is not configured on this bot.",
        "ru": "📷 <b>Анализ фото недоступен</b>\n\nGemini API не настроен на этом боте.",
    },
    "chat_vision_failed": {
        "en": (
            "⚠️ <b>Could not analyze the photo</b>\n\n"
            "Try again later. For text chat, choose a non-Gemini model in 🤖 <b>Models</b>."
        ),
        "ru": (
            "⚠️ <b>Не удалось проанализировать фото</b>\n\n"
            "Попробуй позже. Для текста выбери не-Gemini модель в 🤖 <b>Модели</b>."
        ),
    },
    "chat_rate_limited": {
        "en": (
            "⏳ <b>Model is overloaded</b>\n\n"
            "<b>{model}</b> has reached its request limit.\n\n"
            "Choose another model 👇"
        ),
        "ru": (
            "⏳ <b>Модель перегружена</b>\n\n"
            "<b>{model}</b> достигла лимита запросов.\n\n"
            "Выбери другую модель 👇"
        ),
    },
    "chat_provider_limit": {
        "en": (
            "💳 <b>Model temporarily unavailable</b>\n\n"
            "<b>{model}</b> is not available right now due to provider limits.\n\n"
            "Choose another model 👇"
        ),
        "ru": (
            "💳 <b>Модель временно недоступна</b>\n\n"
            "<b>{model}</b> сейчас недоступна из-за лимитов провайдера.\n\n"
            "Выбери другую модель 👇"
        ),
    },
    "chat_model_gone": {
        "en": (
            "❌ <b>Model unavailable</b>\n\n"
            "<b>{model}</b> was decommissioned by the provider.\n\n"
            "Choose another model 👇"
        ),
        "ru": (
            "❌ <b>Модель недоступна</b>\n\n"
            "<b>{model}</b> отключена провайдером.\n\n"
            "Выбери другую модель 👇"
        ),
    },
    "chat_context_large": {
        "en": (
            "📝 <b>Conversation context is too large</b>\n\n"
            "Start a new chat with /newchat or tap <b>{new_chat_btn}</b> — "
            "this will clear the history so you can continue."
        ),
        "ru": (
            "📝 <b>История чата слишком большая</b>\n\n"
            "Начни новый диалог через /newchat или нажми <b>{new_chat_btn}</b> — "
            "история очистится и можно продолжить."
        ),
    },
    "chat_model_error": {
        "en": "⚠️ <b>Model error</b>\n\nTry again or choose a different model 👇",
        "ru": "⚠️ <b>Ошибка модели</b>\n\nПопробуй снова или выбери другую модель 👇",
    },
    "chat_image_too_large": {
        "en": "Image is too large. Maximum size is 4 MB.",
        "ru": "Изображение слишком большое. Максимум 4 МБ.",
    },
    "chat_image_download_failed": {
        "en": "⚠️ Could not download the image. Please try again.",
        "ru": "⚠️ Не удалось загрузить изображение. Попробуй снова.",
    },
    "chat_photo_status_left_switched": {
        "en": "📷 Left image mode — switched to <b>{model}</b>, analyzing photo...",
        "ru": "📷 Вышел из режима картинок — переключился на <b>{model}</b>, анализирую фото...",
    },
    "chat_photo_status_left": {
        "en": "📷 Left image mode — analyzing photo with <b>{model}</b>...",
        "ru": "📷 Вышел из режима картинок — анализирую фото через <b>{model}</b>...",
    },
    "chat_photo_status_switched": {
        "en": "📷 Switched to <b>{model}</b> — analyzing photo...",
        "ru": "📷 Переключился на <b>{model}</b> — анализирую фото...",
    },
    "chat_photo_status": {
        "en": "📷 Analyzing with <b>{model}</b>...",
        "ru": "📷 Анализирую через <b>{model}</b>...",
    },
    "ratelimit": {
        "en": (
            "⏱ <b>Too many requests</b>\n\n"
            "Please wait <b>{seconds} sec.</b> before sending the next message."
        ),
        "ru": (
            "⏱ <b>Слишком много сообщений</b>\n\n"
            "Подожди <b>{seconds} сек.</b> перед следующим сообщением."
        ),
    },
    "processing_wait": {
        "en": "⏳ Please wait, I'm still processing your previous request...",
        "ru": "⏳ Подожди, я ещё обрабатываю предыдущий запрос...",
    },
    # payment
    "pay_msg_not_found": {
        "en": "Message not found. Try /buy again.",
        "ru": "Сообщение не найдено. Попробуй /buy снова.",
    },
    "pay_invoice_title": {
        "en": "Unlimited Subscription — 30 days",
        "ru": "Безлимитная подписка — 30 дней",
    },
    "pay_invoice_desc": {
        "en": (
            "Unlimited text + image requests to all models for {days} days. "
            "Fair-use: {rate_limit} messages per {rate_window} sec."
        ),
        "ru": (
            "Безлимитные текстовые и графические запросы ко всем моделям на {days} дн. "
            "Лимит: {rate_limit} сообщений за {rate_window} сек."
        ),
    },
    "pay_invoice_label": {
        "en": "{days}-day Subscription",
        "ru": "Подписка на {days} дн.",
    },
    "pay_create_failed": {
        "en": "Failed to create payment. Please try again later.",
        "ru": "Не удалось создать платёж. Попробуй позже.",
    },
    "pay_start_failed": {
        "en": (
            "❌ <b>Payment could not be started.</b>\n\n"
            "If the error persists:\n"
            "1. Make sure you have enough ⭐ on your balance (need {price} ⭐)\n"
            "2. Tap <b>Buy Stars</b> in /buy to top up via PremiumBot\n"
            "3. Write to /paysupport\n\n"
            "<i>Technical details: {details}</i>"
        ),
        "ru": (
            "❌ <b>Не удалось начать оплату.</b>\n\n"
            "Если ошибка повторяется:\n"
            "1. Проверь баланс ⭐ (нужно {price} ⭐)\n"
            "2. Нажми <b>Купить Stars</b> в /buy через PremiumBot\n"
            "3. Напиши в /paysupport\n\n"
            "<i>Технические детали: {details}</i>"
        ),
    },
    "pay_invalid_order": {
        "en": "Invalid order. Please start again with /buy.",
        "ru": "Неверный заказ. Начни заново через /buy.",
    },
    "pay_unknown_order": {
        "en": "Payment received, but the order could not be identified. Please contact /paysupport.",
        "ru": "Платёж получен, но заказ не распознан. Напиши в /paysupport.",
    },
    "pay_activation_failed": {
        "en": "Payment received, but subscription could not be activated. Please contact /paysupport.",
        "ru": "Платёж получен, но подписку не удалось активировать. Напиши в /paysupport.",
    },
    "paysupport": {
        "en": (
            "💬 <b>Payment Support</b>\n\n"
            "If you have issues paying with Telegram Stars:\n\n"
            "1. You need at least <b>{price} ⭐</b> on your balance\n"
            "2. Open /buy and tap <b>Buy Stars</b> — PremiumBot opens inline\n"
            "3. Alternative link: {stars_url}\n"
            "4. If you see <code>PROVIDER_ACCOUNT_INVALID</code>, "
            "try another card or Telegram Desktop\n"
            "5. After buying stars, tap <b>Subscribe</b> in /buy\n\n"
            "If the problem persists, describe the error and send a screenshot here. "
            "We will help manually."
        ),
        "ru": (
            "💬 <b>Поддержка по оплате</b>\n\n"
            "Если проблемы с оплатой через Telegram Stars:\n\n"
            "1. Нужно минимум <b>{price} ⭐</b> на балансе\n"
            "2. Открой /buy и нажми <b>Купить Stars</b> — PremiumBot откроется здесь\n"
            "3. Альтернативная ссылка: {stars_url}\n"
            "4. Если видишь <code>PROVIDER_ACCOUNT_INVALID</code>, "
            "попробуй другую карту или Telegram Desktop\n"
            "5. После покупки Stars нажми <b>Подписка</b> в /buy\n\n"
            "Если проблема остаётся — опиши ошибку и пришли скриншот. Поможем вручную."
        ),
    },
    # image
    "image_help_waiting": {
        "en": (
            "🎨 <b>Describe your image in one message</b>\n\n"
            "Model: <b>{model}</b>{cost_suffix}\n"
            "Example: <code>astronaut cat on the Moon</code>\n\n"
            "Change model → /imagemodels"
        ),
        "ru": (
            "🎨 <b>Опиши картинку в одном сообщении</b>\n\n"
            "Модель: <b>{model}</b>{cost_suffix}\n"
            "Пример: <code>кот-астронавт на Луне</code>\n\n"
            "Сменить модель → /imagemodels"
        ),
    },
    "image_help": {
        "en": (
            "🎨 <b>Image Generation</b>\n\n"
            "Model: <b>{model}</b>{cost_suffix}\n\n"
            "Send a command:\n"
            "<code>/image astronaut cat on the Moon</code>\n\n"
            "Change model → /imagemodels"
        ),
        "ru": (
            "🎨 <b>Генерация картинок</b>\n\n"
            "Модель: <b>{model}</b>{cost_suffix}\n\n"
            "Отправь команду:\n"
            "<code>/image кот-астронавт на Луне</code>\n\n"
            "Сменить модель → /imagemodels"
        ),
    },
    "image_prompt_too_long": {
        "en": "❌ Description is too long. Maximum 1000 characters.",
        "ru": "❌ Описание слишком длинное. Максимум 1000 символов.",
    },
    "image_not_enough": {
        "en": (
            "❌ <b>Not enough requests</b>\n\n"
            "<b>{model}</b> costs <b>{cost}</b> requests.\n"
            "You have: <b>{credits}</b>\n\n"
            "Try a free model → /imagemodels\n"
            "Unlimited access → /buy"
        ),
        "ru": (
            "❌ <b>Недостаточно запросов</b>\n\n"
            "<b>{model}</b> стоит <b>{cost}</b> запросов.\n"
            "На балансе: <b>{credits}</b>\n\n"
            "Попробуй бесплатную модель → /imagemodels\n"
            "Безлимит → /buy"
        ),
    },
    "image_drawing": {
        "en": "🎨 Drawing with <b>{model}</b>... Please wait 10–40 sec.",
        "ru": "🎨 Рисую через <b>{model}</b>... Подожди 10–40 сек.",
    },
    "image_busy": {
        "en": "⏳ Service is busy. Please try again in a minute.",
        "ru": "⏳ Сервис перегружен. Попробуй через минуту.",
    },
    "image_model_unavailable": {
        "en": "💳 <b>{model}</b> is temporarily unavailable.\n\nTry a free model → /imagemodels",
        "ru": "💳 <b>{model}</b> временно недоступна.\n\nПопробуй бесплатную модель → /imagemodels",
    },
    "image_text_instead": {
        "en": "⚠️ The model returned text instead of an image.\nTry rephrasing your description.",
        "ru": "⚠️ Модель вернула текст вместо картинки.\nПопробуй переформулировать описание.",
    },
    "image_failed": {
        "en": "⚠️ Could not create the image. Try another model → /imagemodels",
        "ru": "⚠️ Не удалось создать картинку. Попробуй другую модель → /imagemodels",
    },
    "image_failed_later": {
        "en": "⚠️ Could not create the image. Please try again later.",
        "ru": "⚠️ Не удалось создать картинку. Попробуй позже.",
    },
    "image_spend_failed": {
        "en": "❌ Not enough requests to complete this action.",
        "ru": "❌ Недостаточно запросов для этого действия.",
    },
    "image_send_failed": {
        "en": "⚠️ Image was generated but could not be sent. Please try again.",
        "ru": "⚠️ Картинка создана, но не отправилась. Попробуй снова.",
    },
    "image_cancel_nothing": {
        "en": "Nothing to cancel.",
        "ru": "Нечего отменять.",
    },
    "image_cancelled": {
        "en": "❌ Image generation cancelled.",
        "ru": "❌ Генерация картинки отменена.",
    },
    # image models
    "image_models_title": {
        "en": (
            "🖼 <b>Image Models</b>\n\n"
            "Current: <b>{model}</b>{cost_suffix}\n\n"
            "Pick a model or just describe your image in the <b>next message</b> 👇"
            "{hidden_note}"
        ),
        "ru": (
            "🖼 <b>Модели картинок</b>\n\n"
            "Сейчас: <b>{model}</b>{cost_suffix}\n\n"
            "Выбери модель или опиши картинку в <b>следующем сообщении</b> 👇"
            "{hidden_note}"
        ),
    },
    "image_models_hidden": {
        "en": "\n\n<i>Premium image models are hidden until OpenRouter credits are available.</i>",
        "ru": "\n\n<i>Премиум-модели скрыты, пока нет кредитов OpenRouter.</i>",
    },
    "image_models_ready": {
        "en": (
            "🎨 <b>Ready to draw</b> — model: <b>{model}</b>\n\n"
            "Describe your image in the <b>next message</b>.\n"
            "Example: <code>astronaut cat on the Moon</code>"
        ),
        "ru": (
            "🎨 <b>Готов рисовать</b> — модель: <b>{model}</b>\n\n"
            "Опиши картинку в <b>следующем сообщении</b>.\n"
            "Пример: <code>кот-астронавт на Луне</code>"
        ),
    },
    "image_model_unavailable_alert": {
        "en": "This model is currently unavailable.",
        "ru": "Эта модель сейчас недоступна.",
    },
    "image_model_selected_describe": {
        "en": "✅ {model} — describe your image",
        "ru": "✅ {model} — опиши картинку",
    },
    "image_model_selected": {
        "en": "✅ {model}",
        "ru": "✅ {model}",
    },
    # music
    "music_disabled": {
        "en": (
            "🎵 <b>Music generation is temporarily unavailable</b>\n\n"
            "This feature will return when a free music API is available."
        ),
        "ru": (
            "🎵 <b>Генерация музыки временно недоступна</b>\n\n"
            "Функция вернётся, когда появится бесплатный API."
        ),
    },
    "music_unavailable": {
        "en": (
            "🎵 <b>Music generation is not available</b>\n\n"
            "Pollinations API key is missing. Ask the bot admin to add "
            "<code>POLLINATIONS_API_KEY</code> to <code>.env</code>.\n"
            "Get a key: https://enter.pollinations.ai"
        ),
        "ru": (
            "🎵 <b>Генерация музыки недоступна</b>\n\n"
            "Нет ключа Pollinations API. Попроси админа добавить "
            "<code>POLLINATIONS_API_KEY</code> в <code>.env</code>.\n"
            "Ключ: https://enter.pollinations.ai"
        ),
    },
    "music_help_waiting": {
        "en": (
            "🎵 <b>Describe your music in one message</b>\n\n"
            "Model: <b>{model}</b> ({cost}, ~{duration}s)\n"
            "Example: <code>upbeat electronic dance track with synths</code>\n\n"
            "Change model → /musicmodels"
        ),
        "ru": (
            "🎵 <b>Опиши музыку в одном сообщении</b>\n\n"
            "Модель: <b>{model}</b> ({cost}, ~{duration} сек.)\n"
            "Пример: <code>энергичный электронный трек с синтами</code>\n\n"
            "Сменить модель → /musicmodels"
        ),
    },
    "music_help": {
        "en": (
            "🎵 <b>Music Generation</b>\n\n"
            "Model: <b>{model}</b> ({cost}, ~{duration}s)\n\n"
            "Send a command:\n"
            "<code>/music upbeat electronic dance track</code>\n\n"
            "Change model → /musicmodels"
        ),
        "ru": (
            "🎵 <b>Генерация музыки</b>\n\n"
            "Модель: <b>{model}</b> ({cost}, ~{duration} сек.)\n\n"
            "Отправь команду:\n"
            "<code>/music энергичный электронный трек</code>\n\n"
            "Сменить модель → /musicmodels"
        ),
    },
    "music_not_enough": {
        "en": (
            "❌ <b>Not enough requests</b>\n\n"
            "<b>{model}</b> costs <b>{cost}</b> requests.\n"
            "You have: <b>{credits}</b>\n\n"
            "Try a free model → /musicmodels\n"
            "Unlimited access → /buy"
        ),
        "ru": (
            "❌ <b>Недостаточно запросов</b>\n\n"
            "<b>{model}</b> стоит <b>{cost}</b> запросов.\n"
            "На балансе: <b>{credits}</b>\n\n"
            "Попробуй бесплатную модель → /musicmodels\n"
            "Безлимит → /buy"
        ),
    },
    "music_composing": {
        "en": "🎵 Composing with <b>{model}</b>... Please wait 30–90 sec.",
        "ru": "🎵 Создаю через <b>{model}</b>... Подожди 30–90 сек.",
    },
    "music_api_invalid": {
        "en": "🔑 Music API key is invalid. Contact the bot admin.",
        "ru": "🔑 Неверный ключ Music API. Свяжись с админом бота.",
    },
    "music_credits_depleted": {
        "en": "💳 <b>Music service credits depleted</b>\n\nTry again later or contact the bot admin.",
        "ru": "💳 <b>Кредиты музыкального сервиса закончились</b>\n\nПопробуй позже или свяжись с админом.",
    },
    "music_failed": {
        "en": "⚠️ Could not create the music. Try another model → /musicmodels",
        "ru": "⚠️ Не удалось создать музыку. Попробуй другую модель → /musicmodels",
    },
    "music_failed_later": {
        "en": "⚠️ Could not create the music. Please try again later.",
        "ru": "⚠️ Не удалось создать музыку. Попробуй позже.",
    },
    "music_send_failed": {
        "en": "⚠️ Music was generated but could not be sent. Please try again.",
        "ru": "⚠️ Музыка создана, но не отправилась. Попробуй снова.",
    },
    "music_cancel_nothing": {
        "en": "Nothing to cancel.",
        "ru": "Нечего отменять.",
    },
    "music_cancelled": {
        "en": "❌ Music generation cancelled.",
        "ru": "❌ Генерация музыки отменена.",
    },
    "music_models_not_configured": {
        "en": (
            "🎵 <b>Music generation is not configured</b>\n\n"
            "The bot needs a Pollinations API key.\n"
            "Get one at https://enter.pollinations.ai and add "
            "<code>POLLINATIONS_API_KEY</code> to <code>.env</code>."
        ),
        "ru": (
            "🎵 <b>Генерация музыки не настроена</b>\n\n"
            "Боту нужен ключ Pollinations API.\n"
            "Получи на https://enter.pollinations.ai и добавь "
            "<code>POLLINATIONS_API_KEY</code> в <code>.env</code>."
        ),
    },
    "music_models_title": {
        "en": (
            "🎵 <b>Music Models</b>\n\n"
            "Current: <b>{model}</b> ({cost}, ~{duration}s)\n\n"
            "Pick a model, then send /music or tap {create_btn}."
        ),
        "ru": (
            "🎵 <b>Модели музыки</b>\n\n"
            "Сейчас: <b>{model}</b> ({cost}, ~{duration} сек.)\n\n"
            "Выбери модель, затем /music или {create_btn}."
        ),
    },
    "music_not_configured_alert": {
        "en": "Music is not configured on this bot.",
        "ru": "Музыка не настроена на этом боте.",
    },
}
