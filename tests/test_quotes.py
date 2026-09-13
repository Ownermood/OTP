"""Real Telegram reply/quote parameter construction.

No fake blockquote HTML -- these exercise the actual aiogram ReplyParameters
and Message.quote (TextQuote) types.
"""

from datetime import datetime

from aiogram.types import Chat, Message, TextQuote

from app.utils.quotes import build_reply_parameters


def _message(*, reply_to: Message | None = None, quote: TextQuote | None = None) -> Message:
    return Message(
        message_id=42,
        date=datetime.now(),
        chat=Chat(id=555, type="private"),
        text="the reason",
        reply_to_message=reply_to,
        quote=quote,
    )


def _original(message_id: int = 10) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(),
        chat=Chat(id=555, type="private"),
        text="please provide the exact bank reference for order #5",
    )


def test_no_reply_produces_no_reply_parameters():
    """Never fabricate a reply-to relationship that never existed."""
    message = _message(reply_to=None)

    assert build_reply_parameters(message) is None


def test_a_plain_reply_preserves_message_id_and_chat_id():
    original = _original(message_id=10)
    message = _message(reply_to=original)

    params = build_reply_parameters(message)

    assert params is not None
    assert params.message_id == 10
    assert params.chat_id == 555
    assert params.quote is None


def test_an_exact_client_quote_is_preserved_verbatim():
    """The quote text must match the client's selection exactly -- never
    approximated or re-derived from the full message."""
    original = _original(message_id=10)
    quote = TextQuote(text="exact bank reference", position=18)
    message = _message(reply_to=original, quote=quote)

    params = build_reply_parameters(message)

    assert params is not None
    assert params.quote == "exact bank reference"
    assert params.quote_position == 18


def test_no_client_quote_means_no_fabricated_quote_text():
    """A reply with no client-selected quote must not invent one."""
    original = _original()
    message = _message(reply_to=original, quote=None)

    params = build_reply_parameters(message)

    assert params is not None
    assert params.quote is None
    assert params.quote_position is None
