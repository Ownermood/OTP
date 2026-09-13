"""Real Telegram reply/quote support.

Uses aiogram's actual ``ReplyParameters``/``TextQuote`` types (verified
present in the installed aiogram version) -- never a fake blockquote splice.
If the incoming message was not itself a reply, this returns ``None`` and
the caller sends a normal message: no fabricated reply-to relationship.
"""

from __future__ import annotations

from aiogram.types import Message, ReplyParameters


def build_reply_parameters(message: Message) -> ReplyParameters | None:
    """Reconstruct genuine reply/quote parameters from an incoming message.

    Preserves the original message id, chat id, and -- only when Telegram
    itself reports the user manually quoted a specific portion of text
    (``message.quote``, populated when they use the client's "Reply" with a
    text selection) -- that exact quoted text, its entities and its
    position. A quote is never invented: with no ``message.quote``, the
    reply still threads to the right message, just without a quote excerpt.
    """
    if message.reply_to_message is None:
        return None

    quote = message.quote
    return ReplyParameters(
        message_id=message.reply_to_message.message_id,
        chat_id=message.chat.id,
        quote=quote.text if quote else None,
        quote_entities=quote.entities if quote else None,
        quote_position=quote.position if quote else None,
    )
