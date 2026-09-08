"""Referral programme.

Commission is paid on *deposits*, never on balance the user already had, and
each deposit pays out at most once thanks to the ``referral:payment:<id>``
idempotency key. Self-referral and re-linking an existing user are rejected at
the repository level.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.constants import TransactionType
from app.core.logging import get_logger
from app.core.money import apply_percent, to_minor
from app.database.repositories import ReferralRepository, UserRepository
from app.services.wallet import WalletService

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ReferralStats:
    invited: int
    earned: int
    percent: int


class ReferralService:
    def __init__(self, session: AsyncSession, wallet: WalletService, settings: Settings) -> None:
        self._session = session
        self._wallet = wallet
        self._settings = settings
        self._referrals = ReferralRepository(session)
        self._users = UserRepository(session)

    async def link(self, inviter_id: int, invited_id: int) -> bool:
        """Attach a new user to their inviter. False when the invite is invalid."""
        if not self._settings.referral_enabled:
            return False
        if inviter_id == invited_id:
            logger.info("referral.self_referral_blocked", user_id=invited_id)
            return False
        if await self._users.get(inviter_id) is None:
            return False
        linked = await self._referrals.link(inviter_id, invited_id)
        if linked:
            logger.info("referral.linked", inviter=inviter_id, invited=invited_id)
        return linked

    async def pay_commission(self, user_id: int, deposit_amount: int, payment_id: int) -> int:
        """Pay the inviter their cut of a deposit. Returns the amount paid."""
        if not self._settings.referral_enabled:
            return 0
        if deposit_amount < to_minor(self._settings.referral_min_deposit):
            return 0

        inviter_id = await self._referrals.get_inviter(user_id)
        if inviter_id is None:
            return 0

        commission = apply_percent(deposit_amount, self._settings.referral_percent)
        if commission <= 0:
            return 0

        change = await self._wallet.credit(
            inviter_id,
            commission,
            TransactionType.REFERRAL,
            idempotency_key=f"referral:payment:{payment_id}",
            reference=f"payment #{payment_id}",
            description="Referral commission",
        )
        if change.applied:
            await self._referrals.add_earning(inviter_id, user_id, commission)
            logger.info(
                "referral.commission_paid",
                inviter=inviter_id,
                invited=user_id,
                amount=commission,
            )
        return commission if change.applied else 0

    async def stats(self, user_id: int) -> ReferralStats:
        user = await self._users.get(user_id)
        return ReferralStats(
            invited=await self._referrals.count_invited(user_id),
            earned=user.referral_earned if user else 0,
            percent=int(self._settings.referral_percent),
        )

    async def history(self, user_id: int):
        return await self._referrals.list_for_inviter(user_id)

    def link_for(self, bot_username: str, user_id: int) -> str:
        return f"https://t.me/{bot_username}?start=ref{user_id}"

    @staticmethod
    def parse_start_payload(payload: str) -> int | None:
        """Extract an inviter id from a ``/start`` deep link payload."""
        if payload.startswith("ref") and payload[3:].isdigit():
            return int(payload[3:])
        return None
