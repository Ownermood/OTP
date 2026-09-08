"""Admin panel.

Access is decided by :func:`app.services.admin.can` against the role
configured in ``ADMIN_IDS``/``ADMIN_ROLES`` -- never by anything in callback
data. Every mutating action writes an audit row.

The sections share one router, defined in :mod:`.common`; importing the
section modules is what registers their handlers on it.
"""

from app.bot.handlers.admin import (  # noqa: F401  -- imported for registration
    broadcast,
    dashboard,
    promo,
    records,
    users,
)
from app.bot.handlers.admin.common import router

__all__ = ["router"]
