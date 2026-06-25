from urllib.parse import quote

from aiogram.types import Message

from config import (
    DAILY_FREE_CREDITS,
    REFERRAL_BONUS_CREDITS,
    FREE_CREDITS_ON_START,
    SUBSCRIPTION_PRICE_STARS,
)

SHARE_TEXT = (
    "Free AI in Telegram — chat with Llama, Gemini, DeepSeek and more. Try it:"
)


def referral_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref{user_id}"


def share_url(bot_username: str, user_id: int) -> str:
    link = referral_link(bot_username, user_id)
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(SHARE_TEXT)}"


def out_of_credits_text(credits: int) -> str:
    return (
        f"❌ <b>Out of requests</b>\n\n"
        f"You have: <b>{credits}</b>\n\n"
        f"<b>Get more for free:</b>\n"
        f"• Tomorrow — <b>+{DAILY_FREE_CREDITS}</b> daily requests 🎁\n"
        f"• Invite a friend — <b>+{REFERRAL_BONUS_CREDITS}</b> per signup 👥\n\n"
        f"<b>Or unlimited access:</b>\n"
        f"1. Tap <b>⭐ Buy Stars</b> (PremiumBot opens inline)\n"
        f"2. Then tap <b>💎 Subscribe</b> — <b>{SUBSCRIPTION_PRICE_STARS} ⭐/month</b>"
    )


def low_credits_text(credits: int) -> str:
    word = "request" if credits == 1 else "requests"
    return (
        f"⚠️ <b>{credits} {word} left</b>\n\n"
        f"Invite friends via 👥 <b>Referral</b> (+{REFERRAL_BONUS_CREDITS} each) "
        f"or get unlimited → 💎 <b>Subscription</b>"
    )


def referral_program_text(ref_link: str) -> str:
    return (
        f"👥 <b>Invite friends — earn free requests</b>\n\n"
        f"Share your link. When a <b>new user</b> starts the bot:\n"
        f"• You get <b>+{REFERRAL_BONUS_CREDITS} requests</b>\n"
        f"• They get <b>{FREE_CREDITS_ON_START} requests</b> to start\n\n"
        f"Unlimited users can still earn referral bonuses.\n\n"
        f"🔗 <b>Your link:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"Tap <b>Share bot</b> below — pick a chat and send 👇"
    )


def balance_free_tier_text(credits: int, daily_added: bool) -> str:
    daily_line = f"\n✅ <b>+{DAILY_FREE_CREDITS} daily requests added!</b>" if daily_added else ""
    return (
        f"💰 <b>Your Balance</b>\n\n"
        f"Requests: <b>{credits}</b>{daily_line}\n\n"
        f"<b>Free ways to get more:</b>\n"
        f"• <b>+{DAILY_FREE_CREDITS}</b> every day — open 💰 Balance\n"
        f"• <b>+{REFERRAL_BONUS_CREDITS}</b> per friend — 👥 Referral\n\n"
        f"💎 Unlimited: <b>{SUBSCRIPTION_PRICE_STARS} ⭐/month</b>\n"
        f"Tap <b>⭐ Buy Stars</b> then <b>💎 Subscribe</b> below"
    )


async def answer_out_of_credits(message: Message, db_user) -> None:
    from bot.keyboards.main import growth_keyboard

    bot_info = await message.bot.get_me()
    await message.answer(
        out_of_credits_text(db_user.credits),
        parse_mode="HTML",
        reply_markup=growth_keyboard(bot_info.username, db_user.id),
    )


async def answer_low_credits_hint(message: Message, db_user, credits_left: int) -> None:
    from bot.keyboards.main import growth_keyboard

    bot_info = await message.bot.get_me()
    await message.answer(
        low_credits_text(credits_left),
        parse_mode="HTML",
        reply_markup=growth_keyboard(bot_info.username, db_user.id),
    )
