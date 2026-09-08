"""Uploading the payment QR from inside the bot.

This is the screen that decides where every user's money goes, so the tests
are about who can change it, that the change reaches users, and that it is on
the record.
"""

import pytest

from tests.flow_helpers import REVIEW_CHANNEL


@pytest.fixture
def owner_harness(harness, settings):
    """UPI on, and the driving user is the owner."""
    harness.dispatcher.workflow_data["payment_providers"] = {}
    settings.cryptobot_enabled = False
    settings.telegram_stars_enabled = False
    settings.manual_payment_enabled = True
    settings.manual_payment_channel_id = REVIEW_CHANNEL
    settings.admin_ids = [harness.user_id]
    settings.admin_roles = {}
    return harness


async def _upload_qr(h, file_id: str = "my-branded-qr") -> None:
    """Upload a QR. The button reads Upload the first time, Replace after."""
    await h.send("/admin")
    await h.tap("Payment QR")
    await h.tap("Replace QR" if any("Replace" in b for b in h.buttons()) else "Upload QR")
    await h.send_photo(file_id)


# -- uploading --------------------------------------------------------------


async def test_the_panel_says_what_users_currently_see(owner_harness):
    h = owner_harness
    await h.send("/start")
    await h.send("/admin")
    await h.tap("Payment QR")

    assert "PAYMENT QR" in h.text
    assert "No QR has been uploaded" in h.text
    # The env falls back to a generated code, and the screen says so.
    assert "generated per request" in h.text


async def test_uploading_a_qr_stores_it(owner_harness, session_factory):
    from app.database.repositories import SettingRepository
    from app.services.admin import UPI_QR_FILE_ID_KEY

    h = owner_harness
    await h.send("/start")
    await _upload_qr(h)

    assert "PAYMENT QR UPDATED" in h.text
    async with session_factory() as session:
        stored = await SettingRepository(session).get(UPI_QR_FILE_ID_KEY)
    assert stored == "my-branded-qr"


async def test_the_uploaded_qr_is_what_users_are_sent(owner_harness):
    """The whole point: change it here, and the deposit screen changes."""
    h = owner_harness
    await h.send("/start")
    await _upload_qr(h)

    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")

    qr = h.session.sent[-1]
    assert qr.method == "SendPhoto"
    assert qr.payload["photo"] == "my-branded-qr"
    assert "₹500.00" in qr.text


async def test_the_uploaded_qr_beats_a_configured_one(tmp_path, owner_harness, settings):
    """An upload is the most recent, most deliberate choice, so it wins."""
    from decimal import Decimal

    from app.utils.qr import build_upi_link, render_qr

    image = tmp_path / "old.png"
    image.write_bytes(render_qr(build_upi_link("old@okaxis", "Old", Decimal("1"))))
    settings.upi_qr_image = str(image)

    h = owner_harness
    await h.send("/start")
    await _upload_qr(h, "newer-qr")

    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")

    assert h.session.sent[-1].payload["photo"] == "newer-qr"


async def test_replacing_the_qr_takes_effect_immediately(owner_harness):
    h = owner_harness
    await h.send("/start")
    await _upload_qr(h, "first-qr")
    await _upload_qr(h, "second-qr")

    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")

    assert h.session.sent[-1].payload["photo"] == "second-qr"


async def test_removing_the_qr_falls_back_to_the_configured_one(owner_harness):
    h = owner_harness
    await h.send("/start")
    await _upload_qr(h)

    await h.send("/admin")
    await h.tap("Payment QR")
    await h.tap("Remove QR")

    await h.send("/start")
    await h.tap("Balance")
    await h.tap("Add Balance")
    await h.tap("UPI / QR")
    await h.send("500")

    # Back to a generated code, which is a buffer rather than a stored id.
    photo = h.session.sent[-1].payload["photo"]
    assert type(photo).__name__ == "BufferedInputFile"


# -- what is refused --------------------------------------------------------


async def test_a_file_instead_of_a_photo_is_named_not_ignored(owner_harness):
    h = owner_harness
    await h.send("/start")
    await h.send("/admin")
    await h.tap("Payment QR")
    await h.tap("Upload QR")

    await h.send("here, use this one")
    assert "send the qr as a photo" in h.text.lower()


async def test_a_non_admin_cannot_open_the_screen(harness, settings):
    from app.bot.callbacks import AdminCB

    settings.admin_ids = [999999]
    settings.admin_roles = {}

    await harness.send("/start")
    await harness.press(AdminCB(action="qr").pack())

    assert "do not have access" in harness.text


async def test_a_finance_role_cannot_change_where_money_goes(harness, settings):
    """Finance can credit balances, but not redirect every future payment."""
    from app.bot.callbacks import AdminCB
    from app.core.constants import AdminRole

    settings.admin_ids = [111, harness.user_id]
    settings.admin_roles = {harness.user_id: AdminRole.FINANCE}

    await harness.send("/start")
    await harness.press(AdminCB(action="qr").pack())

    assert "do not have access" in harness.text


async def test_a_non_owner_cannot_upload_even_with_the_callback(harness, settings):
    """The upload handler re-checks; reaching it directly is not enough."""
    from app.bot.callbacks import AdminCB
    from app.core.constants import AdminRole

    settings.admin_ids = [111, harness.user_id]
    settings.admin_roles = {harness.user_id: AdminRole.ADMIN}

    await harness.send("/start")
    await harness.press(AdminCB(action="qr_upload").pack())

    assert "do not have access" in harness.text


# -- the record -------------------------------------------------------------


async def test_changing_the_qr_is_audited(owner_harness, session_factory):
    from app.database.repositories import AdminActionRepository

    h = owner_harness
    await h.send("/start")
    await _upload_qr(h)

    async with session_factory() as session:
        actions = await AdminActionRepository(session).recent()

    assert any(a.action == "payment_qr_set" for a in actions)


async def test_removing_the_qr_is_audited(owner_harness, session_factory):
    from app.database.repositories import AdminActionRepository

    h = owner_harness
    await h.send("/start")
    await _upload_qr(h)
    await h.send("/admin")
    await h.tap("Payment QR")
    await h.tap("Remove QR")

    async with session_factory() as session:
        actions = await AdminActionRepository(session).recent()

    assert any(a.action == "payment_qr_cleared" for a in actions)


# -- backups from the panel -------------------------------------------------


async def test_the_owner_can_take_a_backup(owner_harness, tmp_path, settings):
    """The file is sent to the person who asked, and nowhere else."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.database.base import Base

    path = tmp_path / "bot.db"
    url = f"sqlite+aiosqlite:///{path}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    h = owner_harness
    h.dispatcher.workflow_data["engine"] = engine
    settings.database_url = url

    await h.send("/start")
    await h.send("/admin")
    await h.tap("Backup")

    sent = [s for s in h.session.sent if s.method == "SendDocument"]
    assert len(sent) == 1
    assert sent[0].payload["chat_id"] == h.user_id
    assert "DATABASE BACKUP" in sent[0].payload["caption"]
    assert "every user's balance" in sent[0].payload["caption"]

    await engine.dispose()


async def test_taking_a_backup_is_audited(owner_harness, tmp_path, settings, session_factory):
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.database.base import Base
    from app.database.repositories import AdminActionRepository

    path = tmp_path / "bot.db"
    url = f"sqlite+aiosqlite:///{path}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    h = owner_harness
    h.dispatcher.workflow_data["engine"] = engine
    settings.database_url = url

    await h.send("/start")
    await h.send("/admin")
    await h.tap("Backup")

    async with session_factory() as session:
        actions = await AdminActionRepository(session).recent()
    assert any(a.action == "backup" for a in actions)

    await engine.dispose()


async def test_a_non_owner_cannot_take_a_backup(harness, settings):
    """The backup is every user's data; only the owner may pull it."""
    from app.bot.callbacks import AdminCB
    from app.core.constants import AdminRole

    settings.admin_ids = [111, harness.user_id]
    settings.admin_roles = {harness.user_id: AdminRole.ADMIN}

    await harness.send("/start")
    await harness.press(AdminCB(action="backup").pack())

    assert "do not have access" in harness.text
    assert not [s for s in harness.session.sent if s.method == "SendDocument"]


async def test_a_non_sqlite_database_says_so_rather_than_failing(owner_harness, settings):
    settings.database_url = "postgresql+asyncpg://user:pw@db/bot"

    h = owner_harness
    await h.send("/start")
    await h.send("/admin")
    await h.tap("Backup")

    assert "SQLite only" in h.text
    assert "pg_dump" in h.text
