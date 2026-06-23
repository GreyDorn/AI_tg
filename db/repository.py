from datetime import datetime, date, timedelta
from dataclasses import dataclass
from sqlalchemy import select, delete, text
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

