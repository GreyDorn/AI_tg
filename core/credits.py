from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from db.repository import spend_credits, add_credits, get_credit_charge, record_credit_charge
from core.types import CreditCheck, CreditStatus


def can_afford(user: User, cost: int) -> bool:
    return user.has_unlimited_access or user.credits >= cost


async def charge(
    session: AsyncSession,
    user: User,
    cost: int,
    *,
    operation_key: str | None = None,
) -> CreditCheck:
    if user.has_unlimited_access:
        if operation_key and not await get_credit_charge(session, operation_key):
            await record_credit_charge(session, user.id, operation_key, 0)
        return CreditCheck(status=CreditStatus.OK, credits_spent=0)

    if operation_key:
        existing = await get_credit_charge(session, operation_key)
        if existing:
            return CreditCheck(status=CreditStatus.OK, credits_spent=existing.amount)

    if not await spend_credits(session, user.id, cost):
        return CreditCheck(status=CreditStatus.DENIED, credits_spent=0)

    if operation_key:
        recorded = await record_credit_charge(session, user.id, operation_key, cost)
        if not recorded:
            existing = await get_credit_charge(session, operation_key)
            if existing:
                await add_credits(session, user.id, cost)
                return CreditCheck(status=CreditStatus.OK, credits_spent=existing.amount)

    return CreditCheck(status=CreditStatus.OK, credits_spent=cost)


async def refund(session: AsyncSession, user_id: int, amount: int) -> None:
    if amount > 0:
        await add_credits(session, user_id, amount)
