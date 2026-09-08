"""Background workers.

Three or four loops run alongside the dispatcher, one module each. They all
follow the same discipline: one database session per tick, every iteration
wrapped so a single bad order cannot kill the loop, and a sleep that backs
off when there is nothing to do -- controlled polling, not hammering.
"""

from app.services.workers.backup import BackupWorker
from app.services.workers.base import IDLE_INTERVAL, ORPHAN_GRACE_SECONDS, BaseWorker
from app.services.workers.catalogue import CatalogueWorker
from app.services.workers.health import HealthWorker
from app.services.workers.payments import PaymentWorker
from app.services.workers.smm import SmmWorker
from app.services.workers.sms import SmsWorker

__all__ = [
    "IDLE_INTERVAL",
    "ORPHAN_GRACE_SECONDS",
    "BackupWorker",
    "BaseWorker",
    "CatalogueWorker",
    "HealthWorker",
    "PaymentWorker",
    "SmmWorker",
    "SmsWorker",
]
