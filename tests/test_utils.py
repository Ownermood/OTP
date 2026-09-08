"""Pagination, validation, tokens and formatting."""

import pytest

from app.core.exceptions import ValidationError
from app.utils.pagination import paginate
from app.utils.tokens import TokenStore
from app.utils.validators import (
    clean_search_query,
    parse_link,
    parse_positive_int,
    parse_promo_code,
    parse_username,
)

# -- pagination -------------------------------------------------------------


def test_pagination_slices_and_reports():
    page = paginate(list(range(50)), page=2, per_page=10)
    assert list(page.items) == list(range(10, 20))
    assert page.total_pages == 5
    assert page.label == "2/5"
    assert page.has_previous and page.has_next


def test_pagination_clamps_out_of_range_pages():
    assert paginate(list(range(5)), page=99, per_page=10).page == 1
    assert paginate(list(range(5)), page=-3, per_page=10).page == 1


def test_pagination_of_an_empty_list_is_one_empty_page():
    page = paginate([], page=1)
    assert page.total_pages == 1
    assert not page.has_next and not page.has_previous


# -- validators -------------------------------------------------------------


def test_search_query_is_normalised():
    assert clean_search_query("  WhatS   ApP  ") == "whats app"


def test_search_query_is_length_capped():
    assert len(clean_search_query("x" * 200)) == 32


@pytest.mark.parametrize("raw", ["@tester", "tester"])
def test_username_parsing(raw):
    assert parse_username(raw) == "tester"


@pytest.mark.parametrize("raw", ["a", "1abcdef", "has space", "@" * 5])
def test_invalid_usernames_are_rejected(raw):
    with pytest.raises(ValidationError):
        parse_username(raw)


def test_promo_codes_are_upper_cased():
    assert parse_promo_code(" welcome50 ") == "WELCOME50"


@pytest.mark.parametrize("raw", ["ab", "has space", "x" * 40, "bad!"])
def test_invalid_promo_codes_are_rejected(raw):
    with pytest.raises(ValidationError):
        parse_promo_code(raw)


def test_bounded_integer_parsing():
    assert parse_positive_int("24", minimum=4, maximum=720) == 24
    with pytest.raises(ValidationError):
        parse_positive_int("2", minimum=4)
    with pytest.raises(ValidationError):
        parse_positive_int("1000", minimum=4, maximum=720)
    with pytest.raises(ValidationError):
        parse_positive_int("-5")


def test_link_validation():
    assert parse_link(" https://instagram.com/x ") == "https://instagram.com/x"
    with pytest.raises(ValidationError):
        parse_link("javascript:alert(1)")
    with pytest.raises(ValidationError):
        parse_link("https://" + "x" * 600)


# -- callback tokens --------------------------------------------------------


def test_token_round_trip():
    store = TokenStore()
    token = store.issue(1, price=1_000, service_code="wa")

    assert store.peek(token, 1) == {"price": 1_000, "service_code": "wa"}


def test_token_is_scoped_to_its_owner():
    """A token pasted from another user's session must not resolve."""
    store = TokenStore()
    token = store.issue(1, price=1_000)

    assert store.peek(token, 2) is None
    assert store.consume(token, 2) is None


def test_token_can_only_be_consumed_once():
    """This is what makes a double-tapped confirm button inert."""
    store = TokenStore()
    token = store.issue(1, price=1_000)

    assert store.consume(token, 1) == {"price": 1_000}
    assert store.consume(token, 1) is None


def test_expired_token_does_not_resolve():
    store = TokenStore(ttl=-1)
    token = store.issue(1, price=1_000)

    assert store.peek(token, 1) is None


def test_unknown_token_does_not_resolve():
    assert TokenStore().peek("made-up", 1) is None


# -- formatting -------------------------------------------------------------


def test_html_is_escaped_in_rendered_text():
    from app.utils.formatting import html_escape

    assert html_escape("<script>x</script>") == "&lt;script&gt;x&lt;/script&gt;"


def test_duration_formatting():
    from app.utils.formatting import format_duration

    assert format_duration(4) == "4 hours"
    assert format_duration(24) == "1 day"
    assert format_duration(72) == "3 days"
    assert format_duration(30) == "1 day 6h"


def test_availability_icons():
    from app.utils.formatting import availability_icon

    assert availability_icon(500) == "🟢"
    assert availability_icon(5) == "🟡"
    assert availability_icon(0) == "🔴"
    assert availability_icon(None) == "⚪️"
