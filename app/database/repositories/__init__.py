"""Repositories.

All SQL lives here, one module per entity. Services compose repositories;
handlers never touch a session directly. Repositories flush but do not
commit -- the caller owns the transaction boundary, which is what lets a
purchase debit the wallet and create the order atomically.
"""

from app.database.repositories.base import BaseRepository
from app.database.repositories.favorites import FavoriteRepository
from app.database.repositories.orders import OrderRepository
from app.database.repositories.payments import PaymentRepository
from app.database.repositories.promo import PromoRepository
from app.database.repositories.referrals import ReferralRepository
from app.database.repositories.settings import AdminActionRepository, SettingRepository
from app.database.repositories.transactions import TransactionRepository
from app.database.repositories.users import UserRepository

__all__ = [
    "AdminActionRepository",
    "BaseRepository",
    "FavoriteRepository",
    "OrderRepository",
    "PaymentRepository",
    "PromoRepository",
    "ReferralRepository",
    "SettingRepository",
    "TransactionRepository",
    "UserRepository",
]
