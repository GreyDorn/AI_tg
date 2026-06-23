from datetime import datetime, date, timedelta
from dataclasses import dataclass
from sqlalchemy import select, delete, text, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from config import DATABASE_URL, FREE_CREDITS_ON_START, DAILY_FREE_CREDITS, REFERRAL_BONUS_CREDITS
from db.models import Base, User, Conversation, Message, Payment


engine = create_async_engine(DATABASE_URL)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for column_sql in [
            "ALTER TABLE users ADD COLUMN is_unlimited INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN subscription_until DATETIME",
            "ALTER TABLE users ADD COLUMN current_image_model VARCHAR(64) NOT NULL DEFAULT 'flux-free'",
            "ALTER TABLE users ADD COLUMN waiting_for_image INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN current_music_model VARCHAR(64) NOT NULL DEFAULT 'elevenmusic-free'",
            "ALTER TABLE users ADD COLUMN waiting_for_music INTEGER NOT NULL DEFAULT 0",
        ]:
            try:
                await conn.execute(text(column_sql))
            except Exception:
                pass  # Колонка уже существует


# ── Users ──────────────────────────────────────────────────────────────────────

async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    full_name: str,
    username: str | None,
    referred_by: int | None = None,
) -> tuple[User, bool]:
    """Возвращает (user, is_new)."""
    user = await session.get(User, user_id)
    if user:
        return user, False

    user = User(
        id=user_id,
        full_name=full_name,
        username=username,
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


async def add_credits(session: AsyncSession, user_id: int, amount: int) -> int:
    """Начисляет кредиты. Возвращает новый баланс."""
    user = await session.get(User, user_id)
    if not user:
        return 0
    user.credits += amount
    await session.commit()
    return user.credits


async def claim_daily_credits(session: AsyncSession, user_id: int) -> bool:
    """Начисляет ежедневные кредиты. Возвращает False если уже получены сегодня."""
    user = await session.get(User, user_id)
    if not user:
        return False
    today = date.today()
    if user.daily_credits_claimed_at and user.daily_credits_claimed_at.date() == today:
        return False
    user.credits += DAILY_FREE_CREDITS
    user.daily_credits_claimed_at = datetime.now()
    await session.commit()
    return True


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

