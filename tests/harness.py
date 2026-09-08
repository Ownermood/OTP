"""An in-process Telegram, for driving the real bot without a network.

Real ``Update`` objects go through the real dispatcher: every middleware, every
handler, every keyboard builder and the real locale files. Only the Telegram
API itself is replaced, so what these tests exercise is the wiring that unit
tests cannot reach.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import (
    CallbackQuery,
    Chat,
    InlineKeyboardMarkup,
    Message,
    PhotoSize,
    Update,
)
from aiogram.types import (
    User as TgUser,
)

BOT_ID = 424242
BOT_USERNAME = "test_marketplace_bot"


@dataclass
class Sent:
    """One outbound API call, captured."""

    method: str
    text: str = ""
    markup: InlineKeyboardMarkup | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def buttons(self) -> list[str]:
        if self.markup is None:
            return []
        return [button.text for row in self.markup.inline_keyboard for button in row]

    def callback_for(self, label_fragment: str) -> str | None:
        """The callback data behind the first button whose label contains the text."""
        if self.markup is None:
            return None
        for row in self.markup.inline_keyboard:
            for button in row:
                if label_fragment.lower() in button.text.lower():
                    return button.callback_data
        return None


class MockedSession(BaseSession):
    """Captures outbound calls and answers them with plausible objects."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[Sent] = []
        self._message_id = 1000

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None):
        name = type(method).__name__
        data = method.model_dump(exclude_none=True)
        record = Sent(
            method=name,
            text=str(data.get("text") or data.get("caption") or ""),
            markup=getattr(method, "reply_markup", None),
            payload=data,
        )
        self.sent.append(record)

        if name == "GetMe":
            return TgUser(
                id=BOT_ID, is_bot=True, first_name="Test Bot", username=BOT_USERNAME
            )
        if name in ("SendMessage", "EditMessageText", "SendInvoice", "SendPhoto"):
            self._message_id += 1
            return Message(
                message_id=self._message_id,
                date=datetime.now(),
                chat=Chat(id=int(data.get("chat_id", 1)), type="private"),
                text=record.text,
            )
        # answerCallbackQuery, deleteMessage, answerPreCheckoutQuery, ...
        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover - unused
        yield b""

    async def close(self) -> None:
        return None

    # -- assertions helpers --------------------------------------------

    @property
    def last(self) -> Sent:
        screens = self.screens
        assert screens, "the bot sent nothing"
        return screens[-1]

    #: Calls that put something on the user's screen. Photos count: a QR code
    #: with a caption is a screen, not a side effect.
    SCREEN_METHODS = ("SendMessage", "EditMessageText", "SendPhoto")

    @property
    def screens(self) -> list[Sent]:
        return [s for s in self.sent if s.method in self.SCREEN_METHODS]

    @property
    def alerts(self) -> list[str]:
        """Toast/alert text answered to callbacks, which never enters the chat."""
        return [
            str(s.payload.get("text", ""))
            for s in self.sent
            if s.method == "AnswerCallbackQuery" and s.payload.get("text")
        ]

    def clear(self) -> None:
        self.sent.clear()


class BotHarness:
    """Drives a user through the bot the way Telegram would."""

    def __init__(self, bot: Bot, dispatcher: Dispatcher, session: MockedSession, user_id: int):
        self.bot = bot
        self.dispatcher = dispatcher
        self.session = session
        self.user_id = user_id
        self._update_id = 0
        self._message_id = 500

    @property
    def screen(self) -> Sent:
        return self.session.last

    @property
    def alerts(self) -> list[str]:
        return self.session.alerts

    @property
    def replied(self) -> bool:
        """False when the update was swallowed -- by throttling, for instance."""
        return bool(self.session.screens)

    def forget_last_tap(self) -> None:
        """Clear the duplicate-callback window so a replay reaches the handler.

        Lets a test target the single-use token specifically, rather than
        stopping at the throttle layer in front of it.
        """
        for middleware in self.dispatcher.callback_query.middleware:
            store = getattr(middleware, "_last_callback", None)
            if store is not None:
                store.pop(self.user_id, None)

    @property
    def text(self) -> str:
        return self.screen.text

    def buttons(self) -> list[str]:
        return self.screen.buttons()

    async def send(self, text: str) -> Sent:
        """Deliver a text message from the user."""
        self.session.clear()
        self._update_id += 1
        self._message_id += 1
        message = Message(
            message_id=self._message_id,
            date=datetime.now(),
            chat=Chat(id=self.user_id, type="private"),
            from_user=self._user(),
            text=text,
        )
        await self.dispatcher.feed_update(
            self.bot, Update(update_id=self._update_id, message=message)
        )
        return self.screen

    async def send_photo(self, file_id: str = "proof-file-id") -> Sent | None:
        """Deliver a photo from the user, as a payment screenshot would arrive."""
        self.session.clear()
        self._update_id += 1
        self._message_id += 1
        message = Message(
            message_id=self._message_id,
            date=datetime.now(),
            chat=Chat(id=self.user_id, type="private"),
            from_user=self._user(),
            photo=[
                PhotoSize(
                    file_id=f"{file_id}-small",
                    file_unique_id="u1",
                    width=90,
                    height=160,
                ),
                PhotoSize(
                    file_id=file_id, file_unique_id="u2", width=720, height=1280
                ),
            ],
        )
        await self.dispatcher.feed_update(
            self.bot, Update(update_id=self._update_id, message=message)
        )
        return self.session.screens[-1] if self.session.screens else None

    def posted_to(self, chat_id: int) -> list[Sent]:
        """Everything the bot sent to a specific chat -- the review channel."""
        return [s for s in self.session.sent if s.payload.get("chat_id") == chat_id]

    async def tap(self, label_fragment: str) -> Sent | None:
        """Press the first button whose label contains ``label_fragment``."""
        callback_data = self.screen.callback_for(label_fragment)
        assert callback_data is not None, (
            f"no button matching {label_fragment!r}; visible: {self.buttons()}"
        )
        return await self.press(callback_data)

    async def press(self, callback_data: str) -> Sent | None:
        """Press a button by its raw callback data.

        Returns ``None`` when the bot deliberately sent nothing back.
        """
        previous = self.session.last
        self.session.clear()
        self._update_id += 1
        self._message_id += 1
        message = Message(
            message_id=self._message_id,
            date=datetime.now(),
            chat=Chat(id=self.user_id, type="private"),
            from_user=self._bot_user(),
            text=previous.text,
            reply_markup=previous.markup,
        )
        query = CallbackQuery(
            id=f"cb{self._update_id}",
            from_user=self._user(),
            chat_instance="test",
            data=callback_data,
            message=message,
        )
        await self.dispatcher.feed_update(
            self.bot, Update(update_id=self._update_id, callback_query=query)
        )
        # A swallowed update (throttled, deduped) is a valid outcome, so this
        # returns None rather than asserting that something was sent.
        return self.session.screens[-1] if self.session.screens else None

    def _user(self) -> TgUser:
        return TgUser(
            id=self.user_id, is_bot=False, first_name="Test", username=f"user{self.user_id}"
        )

    def _bot_user(self) -> TgUser:
        return TgUser(id=BOT_ID, is_bot=True, first_name="Test Bot", username=BOT_USERNAME)
