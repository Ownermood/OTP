"""Button styling.

Bot API 9.4 added a ``style`` field to keyboard buttons, so colour is a real
property of the button rather than something faked with emoji in the label.
Telegram accepts exactly three values -- ``success`` (green), ``danger``
(red) and ``primary`` (blue). There is no fourth "secondary" value to send:
"secondary" here means *omitting* ``style`` entirely, which leaves the
client's own neutral default -- sending an invented string is not an option.

Styles are assigned by *meaning*, not by taste, so the same colour always says
the same thing:

* **success** -- buy / confirm / pay / approve / send / enable: the single
  forward action a screen exists for.
* **danger** -- cancel / reject / delete / disable / ban, and nothing else.
  Never used for a merely destructive-sounding label that actually loses
  nothing (e.g. backing out of a confirmation prompt before anything happened).
* **primary** -- everything else that is a real, deliberate action: opening a
  menu section, a fixed navigation entry, adjusting a balance, creating
  something. The broad default for "this button does something and isn't one
  of the other three".
* **secondary (== no style set)** -- back, home, search, info/help, filter,
  pagination, copy, refresh, resend. Also: a dynamic list of records to pick
  from (order rows, payment rows, user search results, service/category
  tiles, country selection) -- styling every row in a paginated list the same
  colour as a real call-to-action drowns the one action that matters.

Add Balance is *primary*, not danger: topping up is money arriving, and a red
button on the one action that funds every purchase reads as a warning against
doing it. Balance navigation carries no style at all.

An enable/disable toggle is styled by the action its *current label* performs,
not by how disruptive that action is in practice: a button reading "Enable X"
is success, one reading "Disable X" is danger, even where enabling is in fact
the more disruptive choice (maintenance mode is exactly this case).

Never more than one ``success`` on a screen. If everything is highlighted,
nothing is.
"""

from __future__ import annotations

from aiogram.types import CopyTextButton, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

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


def copy_keyboard(phone: str | None, code: str | None):
    """A tap-to-copy shortcut for a push notification carrying a number
    and/or a code -- shared by every worker that sends one, so a delivered
    OTP always offers the same one-tap copy regardless of which provider
    found it."""
    builder = InlineKeyboardBuilder()
    row = []
    if code:
        row.append(button("📋 Copy OTP", copy=code))
    if phone:
        row.append(button("📋 Copy Number", copy=phone))
    if not row:
        return None
    builder.row(*row)
    return builder.as_markup()
