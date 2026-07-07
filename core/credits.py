from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from db.repository import spend_credits, add_credits
from core.types import CreditCheck, CreditStatus


def can_afford(user: User, cost: int) -> bool:
    return user.has_unlimited_access or user.credits >= cost


async def charge(session: AsyncSession, user: User, cost: int) -> CreditCheck:
    if user.has_unlimited_access:
        return CreditCheck(status=CreditStatus.OK, credits_spent=0)
    if not await spend_credits(session, user.id, cost):
        return CreditCheck(status=CreditStatus.DENIED, credits_spent=0)
    return CreditCheck(status=CreditStatus.OK, credits_spent=cost)


async def refund(session: AsyncSession, user_id: int, amount: int) -> None:
    if amount > 0:
        await add_credits(session, user_id, amount)
