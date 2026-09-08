"""Reusable pagination, shared by every list in the bot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar

from app.core.constants import PAGE_SIZE

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    """One slice of a list, plus everything a paginator keyboard needs."""

    items: Sequence[T]
    page: int
    total_pages: int
    total_items: int

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def label(self) -> str:
        return f"{self.page}/{self.total_pages}"


def paginate(items: Sequence[T], page: int = 1, per_page: int = PAGE_SIZE) -> Page[T]:
    """Clamp ``page`` into range and return the corresponding slice."""
    total_items = len(items)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    return Page(items[start : start + per_page], page, total_pages, total_items)
