"""Helpers shared by the end-to-end flow tests."""

REVIEW_CHANNEL = -1001234567890


async def fund(session_factory, user_id: int, amount: int) -> None:
    from app.core.constants import TransactionType
    from app.services.wallet import WalletService

    async with session_factory() as session:
        await WalletService(session).credit(
            user_id, amount, TransactionType.DEPOSIT, f"test:fund:{user_id}:{amount}"
        )
        await session.commit()
