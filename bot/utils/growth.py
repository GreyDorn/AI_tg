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
from bot.i18n import (
    t,
    share_text,
    image_share_text,
    milestone_label,
    DEFAULT_LANG,
)


def referral_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref{user_id}"


def share_url(bot_username: str, user_id: int, lang: str = DEFAULT_LANG, *, text: str | None = None) -> str:
    link = referral_link(bot_username, user_id)
    share = text if text is not None else share_text(lang)
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(share)}"


def image_share_url(bot_username: str, user_id: int, lang: str = DEFAULT_LANG) -> str:
    return share_url(bot_username, user_id, lang, text=image_share_text(lang))


def _next_milestone(referral_count: int) -> tuple[int, str] | None:
    for needed, _rtype, _amount, label in REFERRAL_MILESTONES:
        if referral_count < needed:
            return needed, label
    return None


def milestone_progress_text(referral_count: int, lang: str = DEFAULT_LANG) -> str:
    lines = [t("milestone_header", lang)]
    for needed, _rtype, _amount, label in REFERRAL_MILESTONES:
        mark = "✅" if referral_count >= needed else "🔒"
        lines.append(
            t("milestone_row", lang, mark=mark, needed=needed, label=milestone_label(label, lang))
        )
    nxt = _next_milestone(referral_count)
    if nxt:
        needed, label = nxt
        left = needed - referral_count
        lines.append(
            t("milestone_next", lang, left=left, label=milestone_label(label, lang))
        )
    else:
        lines.append(t("milestone_all_done", lang))
    return "\n".join(lines)


def invite_dashboard_text(
    ref_link: str,
    referral_count: int,
    credits: int,
    login_streak: int,
    lang: str = DEFAULT_LANG,
) -> str:
    streak_line = ""
    if login_streak >= 2:
        streak_line = t("invite_streak", lang, days=login_streak)
        if login_streak >= STREAK_BONUS_START:
            bonus = min(login_streak - STREAK_BONUS_START + 1, STREAK_BONUS_MAX)
            streak_line += t("invite_streak_bonus", lang, bonus=bonus)

    return t(
        "invite_dashboard",
        lang,
        count=referral_count,
        credits=credits,
        streak_line=streak_line,
        bonus=REFERRAL_BONUS_CREDITS,
        free_start=FREE_CREDITS_ON_START,
        milestones=milestone_progress_text(referral_count, lang),
        link=ref_link,
    )


def leaderboard_text(entries: list, bot_username: str, lang: str = DEFAULT_LANG) -> str:
    if not entries:
        return t("leaderboard_empty", lang)
    lines = [t("leaderboard_title", lang)]
    medals = ("🥇", "🥈", "🥉")
    for i, entry in enumerate(entries):
        medal = medals[i] if i < 3 else f"{i + 1}."
        name = f"@{entry.username}" if entry.username else entry.full_name[:20]
        lines.append(t("leaderboard_row", lang, medal=medal, name=name, count=entry.referrals))
    lines.append(t("leaderboard_footer", lang))
    return "\n".join(lines)


def out_of_credits_text(credits: int, lang: str = DEFAULT_LANG) -> str:
    return t(
        "out_of_credits",
        lang,
        credits=credits,
        daily=DAILY_FREE_CREDITS,
        bonus=REFERRAL_BONUS_CREDITS,
        price=SUBSCRIPTION_PRICE_STARS,
    )


def low_credits_text(credits: int, lang: str = DEFAULT_LANG) -> str:
    word = t("request_word_one", lang) if credits == 1 else t("request_word_many", lang)
    return t("low_credits", lang, credits=credits, word=word, bonus=REFERRAL_BONUS_CREDITS)


def balance_free_tier_text(
    credits: int,
    daily_added: bool,
    streak_bonus: int = 0,
    login_streak: int = 0,
    lang: str = DEFAULT_LANG,
) -> str:
    daily_line = ""
    if daily_added:
        bonus_part = f" (+{streak_bonus} 🔥)" if streak_bonus else ""
        daily_line = t("balance_daily_added", lang, daily=DAILY_FREE_CREDITS, bonus_part=bonus_part)
    streak_line = ""
    if login_streak >= 2:
        streak_line = t("balance_streak", lang, days=login_streak)
    return t(
        "balance_free",
        lang,
        credits=credits,
        daily_line=daily_line,
        streak_line=streak_line,
        bonus=REFERRAL_BONUS_CREDITS,
        price=SUBSCRIPTION_PRICE_STARS,
    )


def new_referrer_notification_text(
    friend_name: str,
    referral_count: int,
    credits: int,
    lang: str = DEFAULT_LANG,
) -> str:
    return t(
        "new_referrer",
        lang,
        name=friend_name,
        bonus=REFERRAL_BONUS_CREDITS,
        count=referral_count,
        credits=credits,
    )


def milestone_unlocked_text(rewards: list[str], lang: str = DEFAULT_LANG) -> str:
    items = "\n".join(f"• {r}" for r in rewards)
    return t("milestone_unlocked", lang, items=items)


async def answer_out_of_credits(message: Message, db_user, lang: str = DEFAULT_LANG) -> None:
    from bot.keyboards.main import growth_keyboard

    bot_info = await message.bot.get_me()
    await message.answer(
        out_of_credits_text(db_user.credits, lang),
        parse_mode="HTML",
        reply_markup=growth_keyboard(bot_info.username, db_user.id, lang),
    )


async def answer_low_credits_hint(message: Message, db_user, credits_left: int, lang: str = DEFAULT_LANG) -> None:
    from bot.keyboards.main import growth_keyboard

    bot_info = await message.bot.get_me()
    await message.answer(
        low_credits_text(credits_left, lang),
        parse_mode="HTML",
        reply_markup=growth_keyboard(bot_info.username, db_user.id, lang),
    )
