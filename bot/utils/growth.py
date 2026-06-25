from urllib.parse import quote

from aiogram.types import Message

from config import (
    DAILY_FREE_CREDITS,
    REFERRAL_BONUS_CREDITS,
    FREE_CREDITS_ON_START,
    SUBSCRIPTION_PRICE_STARS,
    REFERRAL_MILESTONES,
    STREAK_BONUS_START,
    STREAK_BONUS_MAX,
)

SHARE_TEXT = (
    "🤖 Free AI in Telegram — ChatGPT, Gemini, DeepSeek, photo analysis & image generation. "
    "Works right here, no install. Try it:"
)

IMAGE_SHARE_TEXT = (
    "🎨 I made this with a free AI bot in Telegram — try it yourself:"
)


def referral_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref{user_id}"


def share_url(bot_username: str, user_id: int, text: str = SHARE_TEXT) -> str:
    link = referral_link(bot_username, user_id)
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(text)}"


def image_share_url(bot_username: str, user_id: int) -> str:
    return share_url(bot_username, user_id, IMAGE_SHARE_TEXT)


def _next_milestone(referral_count: int) -> tuple[int, str] | None:
    for needed, _rtype, _amount, label in REFERRAL_MILESTONES:
        if referral_count < needed:
            return needed, label
    return None


def milestone_progress_text(referral_count: int) -> str:
    lines = ["<b>🏆 Referral rewards:</b>"]
    for needed, _rtype, _amount, label in REFERRAL_MILESTONES:
        mark = "✅" if referral_count >= needed else "🔒"
        lines.append(f"{mark} {needed} friends → <b>{label}</b>")
    nxt = _next_milestone(referral_count)
    if nxt:
        needed, label = nxt
        left = needed - referral_count
        lines.append(f"\n<b>Next:</b> invite <b>{left}</b> more → {label}")
    else:
        lines.append("\n🎉 <b>All milestones unlocked!</b> Keep sharing.")
    return "\n".join(lines)


def invite_dashboard_text(
    ref_link: str,
    referral_count: int,
    credits: int,
    login_streak: int,
) -> str:
    streak_line = ""
    if login_streak >= 2:
        streak_line = f"\n🔥 Login streak: <b>{login_streak} days</b>"
        if login_streak >= STREAK_BONUS_START:
            bonus = min(login_streak - STREAK_BONUS_START + 1, STREAK_BONUS_MAX)
            streak_line += f" (+{bonus} extra daily bonus)"

    return (
        f"👥 <b>Invite & Earn</b>\n\n"
        f"Your friends invited: <b>{referral_count}</b>\n"
        f"Balance: <b>{credits}</b> requests{streak_line}\n\n"
        f"<b>Per friend who joins:</b>\n"
        f"• You get <b>+{REFERRAL_BONUS_CREDITS} requests</b>\n"
        f"• They get <b>{FREE_CREDITS_ON_START} requests</b> free\n\n"
        f"{milestone_progress_text(referral_count)}\n\n"
        f"🔗 <b>Your link:</b>\n<code>{ref_link}</code>\n\n"
        f"Tap <b>Share bot</b> — send to groups, friends, channels 👇"
    )


def leaderboard_text(entries: list, bot_username: str) -> str:
    if not entries:
        return (
            "🏆 <b>Top inviters</b>\n\n"
            "No referrals yet — be the first!\n"
            f"Share your link: /invite"
        )
    lines = ["🏆 <b>Top inviters — this month</b>\n"]
    medals = ("🥇", "🥈", "🥉")
    for i, entry in enumerate(entries):
        medal = medals[i] if i < 3 else f"{i + 1}."
        name = f"@{entry.username}" if entry.username else entry.full_name[:20]
        lines.append(f"{medal} {name} — <b>{entry.referrals}</b> friends")
    lines.append(
        f"\nWant to climb the board? → /invite\n"
        f"Top inviters unlock <b>free unlimited</b> access 🎁"
    )
    return "\n".join(lines)


def out_of_credits_text(credits: int) -> str:
    return (
        f"❌ <b>Out of requests</b>\n\n"
        f"You have: <b>{credits}</b>\n\n"
        f"<b>Get more for free:</b>\n"
        f"• Tomorrow — <b>+{DAILY_FREE_CREDITS}</b> daily (+ streak bonus 🔥)\n"
        f"• Invite a friend — <b>+{REFERRAL_BONUS_CREDITS}</b> via /invite 👥\n"
        f"• 10 friends → <b>3 days unlimited</b> free\n\n"
        f"<b>Or unlimited access:</b>\n"
        f"1. Tap <b>⭐ Buy Stars</b> (opens inline)\n"
        f"2. Tap <b>💎 Subscribe</b> — <b>{SUBSCRIPTION_PRICE_STARS} ⭐/month</b>"
    )


def low_credits_text(credits: int) -> str:
    word = "request" if credits == 1 else "requests"
    return (
        f"⚠️ <b>{credits} {word} left</b>\n\n"
        f"Invite friends → /invite (+{REFERRAL_BONUS_CREDITS} each, milestones up to 1 month free)\n"
        f"Or unlimited → 💎 <b>Subscription</b>"
    )


def referral_program_text(ref_link: str) -> str:
    return (
        f"👥 <b>Invite friends — earn free requests & unlimited access</b>\n\n"
        f"Per new friend:\n"
        f"• You: <b>+{REFERRAL_BONUS_CREDITS} requests</b>\n"
        f"• Friend: <b>{FREE_CREDITS_ON_START} requests</b>\n\n"
        f"<b>Milestones:</b>\n"
        f"• 3 friends → +15 bonus requests\n"
        f"• 10 friends → <b>3 days unlimited</b>\n"
        f"• 25 friends → <b>7 days unlimited</b>\n"
        f"• 50 friends → <b>1 month unlimited</b>\n\n"
        f"🔗 <code>{ref_link}</code>\n\n"
        f"See your progress → /invite\n"
        f"Leaderboard → /top"
    )


def balance_free_tier_text(credits: int, daily_added: bool, streak_bonus: int = 0, login_streak: int = 0) -> str:
    daily_line = ""
    if daily_added:
        bonus_part = f" (+{streak_bonus} streak 🔥)" if streak_bonus else ""
        daily_line = f"\n✅ <b>+{DAILY_FREE_CREDITS}{bonus_part} daily requests added!</b>"
    streak_line = ""
    if login_streak >= 2:
        streak_line = f"\n🔥 Streak: <b>{login_streak} days</b> — open daily for bonus requests"
    return (
        f"💰 <b>Your Balance</b>\n\n"
        f"Requests: <b>{credits}</b>{daily_line}{streak_line}\n\n"
        f"<b>Free ways to get more:</b>\n"
        f"• Daily login — /balance\n"
        f"• Invite friends — /invite (+{REFERRAL_BONUS_CREDITS} each)\n"
        f"• Milestones up to <b>1 month free unlimited</b>\n\n"
        f"💎 Unlimited: <b>{SUBSCRIPTION_PRICE_STARS} ⭐/month</b>\n"
        f"Tap <b>⭐ Buy Stars</b> then <b>💎 Subscribe</b>"
    )


def new_referrer_notification_text(friend_name: str, referral_count: int, credits: int) -> str:
    return (
        f"🎉 <b>{friend_name}</b> joined via your link!\n\n"
        f"+<b>{REFERRAL_BONUS_CREDITS} requests</b> added\n"
        f"Total friends: <b>{referral_count}</b>\n"
        f"Balance: <b>{credits}</b>\n\n"
        f"Keep sharing → /invite"
    )


def milestone_unlocked_text(rewards: list[str]) -> str:
    items = "\n".join(f"• {r}" for r in rewards)
    return f"🏆 <b>Referral milestone unlocked!</b>\n\n{items}"


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
