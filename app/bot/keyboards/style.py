"""Button styling.

Bot API 9.4 added a ``style`` field to keyboard buttons, so colour is a real
property of the button rather than something faked with emoji in the label.
Three styles exist -- ``success`` (green), ``danger`` (red) and ``primary``
(blue) -- and omitting it leaves the client's default.

Styles are assigned by *meaning*, not by taste, so the same colour always says
the same thing:

* **success** -- the single forward/confirm action a screen exists for: Buy,
  Confirm, Pay Now, Approve, Buy Now.
* **danger** -- a destructive or irreversible decision: cancelling an
  activation, "Yes, cancel", declining a payment, removing a favourite,
  transferring balance, banning.
* **primary** -- navigation and money-neutral secondary actions that lead
  somewhere: Add Balance, Check Payment, Show All, Search, Track.
* **unstyled** -- inert or incidental, and plain balance/wallet navigation:
  page counters, Back, Home, Balance, help.

Add Balance is *primary*, not danger: topping up is money arriving, and a red
button on the one action that funds every purchase reads as a warning against
doing it. Balance navigation carries no style at all.

Never more than one ``success`` on a screen. If everything is highlighted,
nothing is.
"""

from __future__ import annotations

from aiogram.types import CopyTextButton, InlineKeyboardButton

SUCCESS = "success"
DANGER = "danger"
PRIMARY = "primary"


def button(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    style: str | None = None,
    icon: str | None = None,
    copy: str | None = None,
) -> InlineKeyboardButton:
    """Build a button, applying a style, a custom emoji or a copy payload.

    ``icon`` is a custom (premium) emoji id. Telegram accepts it only from a
    bot that owns a Fragment username, or from a bot whose owner has Telegram
    Premium when the message goes straight to a private, group or supergroup
    chat -- so it stays optional and the button renders fine without one.

    ``copy`` makes a tap copy that exact text to the clipboard (Bot API 8.0).
    A copy button carries nothing else -- no callback, no url.
    """
    return InlineKeyboardButton(
        text=text,
        callback_data=callback_data,
        url=url,
        style=style,
        icon_custom_emoji_id=icon,
        copy_text=CopyTextButton(text=copy) if copy is not None else None,
    )
