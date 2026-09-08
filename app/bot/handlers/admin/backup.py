"""Database backups from the panel.

The file contains every balance, so it is sent to the person who asked for it
and nowhere else, and the request is audited.
"""

from __future__ import annotations

from aiogram import F
from aiogram.types import CallbackQuery, FSInputFile

from app.bot.callbacks import AdminCB
from app.bot.handlers.admin.common import _back_only, _guard, router
from app.bot.handlers.common import build_context, show, toast
from app.core.logging import get_logger
from app.services.backup import BackupService

logger = get_logger(__name__)


@router.callback_query(AdminCB.filter(F.action == "backup"))
async def send_backup(query: CallbackQuery, **data):
    """Take a snapshot and send it to the requesting admin."""
    context = build_context(data)
    role = _guard(context, "backup")

    service = BackupService(data["engine"], context.settings.database_url)
    if not service.supported:
        await show(query, context.text("admin.backup_unsupported"), _back_only())
        return

    await toast(query, context.text("common.loading"))

    async with service.snapshot() as (path, size):
        if service.too_large(size):
            await show(
                query,
                context.text("admin.backup_too_large", size=_megabytes(size)),
                _back_only(),
            )
            return

        await query.bot.send_document(
            chat_id=query.from_user.id,
            document=FSInputFile(path, filename=path.name),
            caption=context.text(
                "admin.backup_ready", name=path.name, size=_megabytes(size)
            ),
        )

    await context.admin.log(query.from_user.id, role, "backup", None, path.name)
    logger.info("backup.sent", admin_id=query.from_user.id, name=path.name)


def _megabytes(size: int) -> str:
    return f"{size / 1024 / 1024:.2f} MB"
