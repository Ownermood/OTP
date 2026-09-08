"""Whole-catalogue listings.

The paginated keyboards are how you *pick* something; these are how you see
everything at once. A user comparing prices across sixty countries should not
have to tap through eight pages of buttons to do it.

Telegram caps a message at 4096 characters, so a listing is split into as many
messages as it needs, each labelled with its position.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

#: Telegram's hard limit, with room for the header we add to each part.
MESSAGE_LIMIT = 3800


@dataclass(frozen=True, slots=True)
class Listing:
    """One message of a multi-part listing."""

    part: int
    total: int
    body: str

    @property
    def is_only(self) -> bool:
        return self.total == 1


def paginate_lines(
    lines: Sequence[str], header: str, limit: int = MESSAGE_LIMIT
) -> list[Listing]:
    """Split rendered lines into messages that fit, keeping lines whole.

    Splitting mid-line would cut a country's price in half, so a line that
    would overflow starts the next message instead.
    """
    if not lines:
        return []

    chunks: list[list[str]] = [[]]
    length = 0
    for line in lines:
        # +1 for the newline that will join it.
        if length + len(line) + 1 > limit and chunks[-1]:
            chunks.append([])
            length = 0
        chunks[-1].append(line)
        length += len(line) + 1

    total = len(chunks)
    return [
        Listing(part=index, total=total, body=f"{header} {index}/{total}\n\n" + "\n".join(chunk))
        if total > 1
        else Listing(part=1, total=1, body=f"{header}\n\n" + "\n".join(chunk))
        for index, chunk in enumerate(chunks, start=1)
    ]


def country_lines(priced: Iterable, currency: str) -> list[str]:
    """One line per country: flag, name, price and stock.

    Stock is what people actually scan for -- a cheap country with nothing in
    it is worse than a dearer one that works -- so it ends the line where the
    eye lands.
    """
    from app.core.countries import dial_code, flag
    from app.core.money import format_money
    from app.utils.formatting import availability_icon

    lines = []
    for item in priced:
        country = item.country
        emoji = country.flag or flag(country.name)
        dial = dial_code(country.name)
        head = " ".join(part for part in (emoji, f"<b>{country.name}</b>", dial) if part)
        stock = "—" if country.available is None else f"{country.available:,}"
        lines.append(
            f"{availability_icon(country.available)} {head} · "
            f"{format_money(item.price, currency)} · {stock}"
        )
    return lines


def service_lines(services: Iterable) -> list[str]:
    """One line per service, with stock where the provider reports it."""
    from app.utils.formatting import availability_icon

    lines = []
    for service in services:
        stock = "" if service.available is None else f" · {service.available:,}"
        lines.append(
            f"{availability_icon(service.available)} <b>{service.name}</b>"
            f" <code>{service.code}</code>{stock}"
        )
    return lines


def offer_lines(priced: Iterable, currency: str) -> list[str]:
    """One line per service available in the chosen country, with its price."""
    from app.core.money import format_money
    from app.utils.formatting import availability_icon

    lines = []
    for item in priced:
        service = item.offer.service
        stock = "" if item.offer.available is None else f" · {item.offer.available:,}"
        lines.append(
            f"{availability_icon(item.offer.available)} <b>{service.name}</b>"
            f" <code>{service.code}</code> · {format_money(item.price, currency)}{stock}"
        )
    return lines


def smm_service_lines(services: Iterable, currency: str) -> list[str]:
    """One line per SMM service: name, rate per 1000 and the order bounds."""
    from app.core.money import format_money

    return [
        f"▫️ <b>{service.name}</b>\n"
        f"    {format_money(service.rate_per_1000, currency)}/1k · "
        f"{service.min_quantity:,}–{service.max_quantity:,}"
        for service in services
    ]
