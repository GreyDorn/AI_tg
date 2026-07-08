from datetime import datetime, date, timedelta
from dataclasses import dataclass
from sqlalchemy import select, delete, text, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from config import (
    DATABASE_URL,
    FREE_CREDITS_ON_START,
    DAILY_FREE_CREDITS,
    REFERRAL_BONUS_CREDITS,
    REFERRAL_MILESTONES,
    STREAK_BONUS_START,
    STREAK_BONUS_MAX,
)
from db.models import Base, User, Conversation, Message, Payment, ProcessedEvent, CreditCharge


engine = create_async_engine(DATABASE_URL)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionFactory() as session:
        await prune_processed_events(session)
        for column_sql in [
            "ALTER TABLE users ADD COLUMN is_unlimited INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN subscription_until DATETIME",
            "ALTER TABLE users ADD COLUMN current_image_model VARCHAR(64) NOT NULL DEFAULT 'flux-free'",
            "ALTER TABLE users ADD COLUMN waiting_for_image INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN current_music_model VARCHAR(64) NOT NULL DEFAULT 'elevenmusic-free'",
            "ALTER TABLE users ADD COLUMN waiting_for_music INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN referral_milestone_level INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN login_streak INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN last_active_date DATETIME",
            "ALTER TABLE users ADD COLUMN daily_reminder_sent_at DATETIME",
            "ALTER TABLE users ADD COLUMN language_code VARCHAR(8) NOT NULL DEFAULT 'en'",
        ]:
            try:
                async with engine.begin() as conn:
                    await conn.execute(text(column_sql))
            except Exception:
                pass  # Колонка уже существует


# ── Idempotency ───────────────────────────────────────────────────────────────

async def prune_processed_events(session: AsyncSession, *, days: int = 30) -> None:
    cutoff = datetime.now() - timedelta(days=days)
    await session.execute(delete(ProcessedEvent).where(ProcessedEvent.created_at < cutoff))
    await session.commit()


async def try_claim_event(session: AsyncSession, event_key: str, source: str) -> bool:
    """Returns True if this event is new and claimed."""
    try:
        session.add(ProcessedEvent(event_key=event_key, source=source))
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def get_credit_charge(session: AsyncSession, operation_key: str) -> CreditCharge | None:
    return await session.get(CreditCharge, operation_key)


async def record_credit_charge(
    session: AsyncSession,
    user_id: int,
    operation_key: str,
    amount: int,
) -> bool:
    """Record a charge. Returns False if operation_key already exists."""
    try:
        session.add(CreditCharge(operation_key=operation_key, user_id=user_id, amount=amount))
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        return False


# ── Users ──────────────────────────────────────────────────────────────────────

def _normalize_language_code(code: str | None) -> str:
    if code and str(code).lower().startswith("ru"):
        return "ru"
    return "en"


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    full_name: str,
    username: str | None,
    referred_by: int | None = None,
    language_code: str | None = None,
) -> tuple[User, bool]:
    """Возвращает (user, is_new)."""
    lang = _normalize_language_code(language_code)
    user = await session.get(User, user_id)
    if user:
        if user.language_code != lang:
            user.language_code = lang
            await session.commit()
        return user, False

    user = User(
        id=user_id,
        full_name=full_name,
        username=username,
        language_code=lang,
        credits=FREE_CREDITS_ON_START,
        referred_by=referred_by if referred_by != user_id else None,
    )
    session.add(user)

    if referred_by and referred_by != user_id:
        referrer = await session.get(User, referred_by)
        if referrer:
            referrer.credits += REFERRAL_BONUS_CREDITS

    await session.commit()
    return user, True


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def update_user_model(session: AsyncSession, user_id: int, model_id: str) -> None:
    user = await session.get(User, user_id)
    if user:
        user.current_model = model_id
        await session.commit()


async def update_user_image_model(session: AsyncSession, user_id: int, model_key: str) -> None:
    user = await session.get(User, user_id)
    if user:
        user.current_image_model = model_key
        await session.commit()


async def set_waiting_for_image(session: AsyncSession, user_id: int, waiting: bool) -> None:
    user = await session.get(User, user_id)
    if user:
        user.waiting_for_image = waiting
        if waiting:
            user.waiting_for_music = False
        await session.commit()


async def update_user_music_model(session: AsyncSession, user_id: int, model_key: str) -> None:
    user = await session.get(User, user_id)
    if user:
        user.current_music_model = model_key
        await session.commit()


async def set_waiting_for_music(session: AsyncSession, user_id: int, waiting: bool) -> None:
    user = await session.get(User, user_id)
    if user:
        user.waiting_for_music = waiting
        if waiting:
            user.waiting_for_image = False
        await session.commit()


async def clear_waiting_modes(session: AsyncSession, user_id: int) -> None:
    """Exit image/music prompt modes (back to normal text chat)."""
    user = await session.get(User, user_id)
    if not user:
        return
    if not user.waiting_for_image and not user.waiting_for_music:
        return
    user.waiting_for_image = False
    user.waiting_for_music = False
    await session.commit()


async def spend_credits(session: AsyncSession, user_id: int, amount: int) -> bool:
    """Списывает кредиты. Возвращает False если недостаточно."""
    user = await session.get(User, user_id)
    if not user or user.credits < amount:
        return False
    user.credits -= amount
    await session.commit()
    return True


async def spend_credits_idempotent(
    session: AsyncSession,
    user_id: int,
    amount: int,
    operation_key: str | None,
) -> bool:
    """Idempotent spend. True = paid or already paid for this operation_key."""
    if operation_key:
        existing = await get_credit_charge(session, operation_key)
        if existing:
            return True
    if not await spend_credits(session, user_id, amount):
        return False
    if operation_key:
        recorded = await record_credit_charge(session, user_id, operation_key, amount)
        if not recorded:
            await add_credits(session, user_id, amount)
            return True
    return True


async def add_credits(session: AsyncSession, user_id: int, amount: int) -> int:
    """Начисляет кредиты. Возвращает новый баланс."""
    user = await session.get(User, user_id)
    if not user:
        return 0
    user.credits += amount
    await session.commit()
    return user.credits


async def claim_daily_credits(session: AsyncSession, user_id: int) -> tuple[bool, int]:
    """Начисляет ежедневные кредиты + streak bonus. Returns (was_claimed, bonus_added)."""
    user = await session.get(User, user_id)
    if not user:
        return False, 0
    today = date.today()
    if user.daily_credits_claimed_at and user.daily_credits_claimed_at.date() == today:
        return False, 0

    yesterday = today - timedelta(days=1)
    if user.last_active_date:
        last_day = user.last_active_date.date()
        if last_day == yesterday:
            user.login_streak += 1
        elif last_day < yesterday:
            user.login_streak = 1
    else:
        user.login_streak = 1

    streak_bonus = 0
    if user.login_streak >= STREAK_BONUS_START:
        streak_bonus = min(user.login_streak - STREAK_BONUS_START + 1, STREAK_BONUS_MAX)

    user.credits += DAILY_FREE_CREDITS + streak_bonus
    user.daily_credits_claimed_at = datetime.now()
    user.last_active_date = datetime.now()
    await session.commit()
    return True, streak_bonus


# ── Conversations ──────────────────────────────────────────────────────────────

async def create_conversation(
    session: AsyncSession, user_id: int, model_id: str
) -> Conversation:
    conv = Conversation(user_id=user_id, model_id=model_id)
    session.add(conv)
    await session.commit()
    return conv


async def get_active_conversation(
    session: AsyncSession, user_id: int
) -> Conversation | None:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ── Messages ───────────────────────────────────────────────────────────────────

async def add_message(
    session: AsyncSession, conversation_id: int, role: str, content: str
) -> Message:
    msg = Message(conversation_id=conversation_id, role=role, content=content)
    session.add(msg)
    await session.commit()
    return msg


async def get_conversation_messages(
    session: AsyncSession, conversation_id: int
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars().all())


async def clear_conversation_messages(
    session: AsyncSession, conversation_id: int
) -> None:
    await session.execute(
        delete(Message).where(Message.conversation_id == conversation_id)
    )
    await session.commit()


async def grant_unlimited(session: AsyncSession, user_id: int) -> bool:
    """Выдаёт постоянный безлимит пользователю (для администраторов)."""
    user = await session.get(User, user_id)
    if not user:
        return False
    user.is_unlimited = True
    await session.commit()
    return True


def _extend_subscription(user: User, days: int) -> datetime:
    now = datetime.now()
    base = user.subscription_until if user.subscription_until and user.subscription_until > now else now
    return base + timedelta(days=days)


@dataclass
class PaymentResult:
    subscription_until: datetime | None
    is_duplicate: bool


async def _get_payment_by_charge_id(session: AsyncSession, charge_id: str) -> Payment | None:
    result = await session.execute(select(Payment).where(Payment.charge_id == charge_id))
    return result.scalar_one_or_none()


async def process_subscription_payment(
    session: AsyncSession,
    user_id: int,
    charge_id: str,
    amount: int,
    payload: str,
    days: int = 30,
) -> PaymentResult:
    """Идемпотентная обработка оплаты подписки по charge_id."""
    existing = await _get_payment_by_charge_id(session, charge_id)
    if existing:
        return PaymentResult(subscription_until=existing.subscription_until, is_duplicate=True)

    user = await session.get(User, user_id)
    if not user:
        return PaymentResult(subscription_until=None, is_duplicate=False)

    subscription_until = _extend_subscription(user, days)
    user.subscription_until = subscription_until

    session.add(
        Payment(
            charge_id=charge_id,
            user_id=user_id,
            amount=amount,
            currency="XTR",
            payload=payload,
            subscription_until=subscription_until,
        )
    )

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await _get_payment_by_charge_id(session, charge_id)
        if existing:
            return PaymentResult(subscription_until=existing.subscription_until, is_duplicate=True)
        raise

    return PaymentResult(subscription_until=subscription_until, is_duplicate=False)


# ── Referral growth ───────────────────────────────────────────────────────────

async def count_referrals(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.count()).select_from(User).where(User.referred_by == user_id)
    )
    return int(result.scalar_one() or 0)


async def mark_daily_reminder_sent(session: AsyncSession, user_id: int) -> None:
    user = await session.get(User, user_id)
    if user:
        user.daily_reminder_sent_at = datetime.now()
        await session.commit()


async def get_users_for_daily_reminder(session: AsyncSession) -> list[User]:
    """Users eligible for a daily bonus reminder (active, not unlimited, not claimed today)."""
    now = datetime.now()
    today = date.today()
    active_since = now - timedelta(days=14)

    result = await session.execute(
        select(User).where(
            User.is_unlimited.is_(False),
            (User.subscription_until.is_(None)) | (User.subscription_until <= now),
        )
    )
    users = []
    for user in result.scalars():
        if user.has_unlimited_access:
            continue
        if user.daily_credits_claimed_at and user.daily_credits_claimed_at.date() == today:
            continue
        if user.daily_reminder_sent_at and user.daily_reminder_sent_at.date() == today:
            continue
        last_touch = user.last_active_date or user.created_at
        if last_touch and last_touch < active_since:
            continue
        users.append(user)
    return users


async def apply_referral_milestones(session: AsyncSession, user_id: int) -> list[str]:
    """Grant newly unlocked referral milestone rewards. Returns list of reward labels."""
    user = await session.get(User, user_id)
    if not user:
        return []

    ref_count = await count_referrals(session, user_id)
    granted: list[str] = []

    for i, (needed, reward_type, amount, label) in enumerate(REFERRAL_MILESTONES):
        if i < user.referral_milestone_level:
            continue
        if ref_count < needed:
            break
        if reward_type == "credits":
            user.credits += amount
        elif reward_type == "days":
            user.subscription_until = _extend_subscription(user, amount)
        user.referral_milestone_level = i + 1
        granted.append(label)

    if granted:
        await session.commit()
    return granted


@dataclass
class LeaderboardEntry:
    user_id: int
    full_name: str
    username: str | None
    referrals: int


async def get_referral_leaderboard(session: AsyncSession, limit: int = 10) -> list[LeaderboardEntry]:
    subq = (
        select(User.referred_by.label("referrer_id"), func.count().label("cnt"))
        .where(User.referred_by.is_not(None))
        .group_by(User.referred_by)
        .order_by(func.count().desc())
        .limit(limit)
    )
    rows = (await session.execute(subq)).all()
    entries: list[LeaderboardEntry] = []
    for referrer_id, cnt in rows:
        referrer = await session.get(User, referrer_id)
        if referrer:
            entries.append(LeaderboardEntry(
                user_id=referrer.id,
                full_name=referrer.full_name,
                username=referrer.username,
                referrals=int(cnt),
            ))
    return entries


# ── Admin stats ───────────────────────────────────────────────────────────────

@dataclass
class BotStats:
    total_users: int
    new_today: int
    new_7d: int
    active_subscribers: int
    unlimited_users: int
    total_user_messages: int
    messages_today: int
    active_users_7d: int
    payments_total: int
    stars_total: int
    payments_30d: int
    stars_30d: int


async def get_bot_stats(session: AsyncSession) -> BotStats:
    now = datetime.now()
    today_start = datetime.combine(date.today(), datetime.min.time())
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    async def count(stmt) -> int:
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    total_users = await count(select(func.count()).select_from(User))
    new_today = await count(
        select(func.count()).select_from(User).where(User.created_at >= today_start)
    )
    new_7d = await count(
        select(func.count()).select_from(User).where(User.created_at >= week_start)
    )
    active_subscribers = await count(
        select(func.count()).select_from(User).where(User.subscription_until > now)
    )
    unlimited_users = await count(
        select(func.count()).select_from(User).where(User.is_unlimited.is_(True))
    )
    total_user_messages = await count(
        select(func.count()).select_from(Message).where(Message.role == "user")
    )
    messages_today = await count(
        select(func.count())
        .select_from(Message)
        .where(Message.role == "user", Message.created_at >= today_start)
    )
    active_users_7d = await count(
        select(func.count(func.distinct(Conversation.user_id)))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Message.role == "user", Message.created_at >= week_start)
    )

    pay_all = await session.execute(
        select(func.count(), func.coalesce(func.sum(Payment.amount), 0)).select_from(Payment)
    )
    payments_total, stars_total = pay_all.one()

    pay_month = await session.execute(
        select(func.count(), func.coalesce(func.sum(Payment.amount), 0))
        .select_from(Payment)
        .where(Payment.created_at >= month_start)
    )
    payments_30d, stars_30d = pay_month.one()

    return BotStats(
        total_users=total_users,
        new_today=new_today,
        new_7d=new_7d,
        active_subscribers=active_subscribers,
        unlimited_users=unlimited_users,
        total_user_messages=total_user_messages,
        messages_today=messages_today,
        active_users_7d=active_users_7d,
        payments_total=int(payments_total or 0),
        stars_total=int(stars_total or 0),
        payments_30d=int(payments_30d or 0),
        stars_30d=int(stars_30d or 0),
    )

