"""Button styling.

Bot API 9.4 added a ``style`` field to keyboard buttons, so colour is a real
property of the button rather than something faked with emoji in the label.
Three styles exist -- ``success`` (green), ``danger`` (red) and ``primary``
(blue) -- and omitting it leaves the client's default.

Styles are assigned by *meaning*, not by taste, so the same colour always says
the same thing:

* **success** -- the one action this screen exists for: buy, confirm, approve.
* **danger** -- money leaving or a decision that cannot be undone: deposits,
  cancelling an activation, declining a payment, deleting.
* **primary** -- navigation and secondary actions that lead somewhere.
* **unstyled** -- inert or incidental: page counters, back, help.

Never more than one ``success`` on a screen. If everything is highlighted,
nothing is.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton

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
) -> InlineKeyboardButton:
    """Build a button, applying a style and a custom emoji when given.

    ``icon`` is a custom (premium) emoji id. Telegram accepts it only from a
    bot that owns a Fragment username, or from a bot whose owner has Telegram
    Premium when the message goes straight to a private, group or supergroup
    chat -- so it stays optional and the button renders fine without one.
    """
    return InlineKeyboardButton(
        text=text,
        callback_data=callback_data,
        url=url,
        style=style,
        icon_custom_emoji_id=icon,
    )
