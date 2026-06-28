"""UI localization: Russian when Telegram language_code starts with 'ru'."""
from __future__ import annotations

from aiogram import F
from aiogram.types import User as TgUser

from db.models import User

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
    return frozenset(v for d in BUTTONS.values() for v in d.values())


def button_filter(key: str):
    return F.text.in_(frozenset(btn(key, lang) for lang in LANGS))


def format_cost(cost: int, lang: str) -> str:
    if cost == 0:
        return t("cost_free", lang)
    if cost == 1:
        return t("cost_one", lang)
    return t("cost_many", lang, cost=cost)


SHARE_TEXT = {
    "en": (
        "🤖 Free AI in Telegram — ChatGPT, Gemini, DeepSeek, photo analysis & image generation. "
        "Works right here, no install. Try it:"
    ),
    "ru": (
        "🤖 Бесплатный AI в Telegram — ChatGPT, Gemini, DeepSeek, анализ фото и генерация картинок. "
        "Работает прямо здесь. Попробуй:"
    ),
}

IMAGE_SHARE_TEXT = {
    "en": "🎨 I made this with a free AI bot in Telegram — try it yourself:",
    "ru": "🎨 Я сделал это в бесплатном AI-боте в Telegram — попробуй:",
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
        "en": "\n\n✨ Free AI art → @{bot_username}",
        "ru": "\n\n✨ Бесплатный AI-арт → @{bot_username}",
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
}
