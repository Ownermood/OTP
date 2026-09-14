"""``matches_search`` is the one place every country picker in the bot (the
SMS marketplace and TG-Lion alike) decides whether a typed query identifies a
country. It must accept a full name, a colloquial short name, an ISO-2 code,
an ISO-3 code, and a calling code -- all case-insensitively -- without
false-positiving on unrelated countries.
"""

from app.core.countries import matches_search


def test_matches_full_name_case_insensitively():
    assert matches_search("India", "india")
    assert matches_search("India", "INDIA")
    assert matches_search("India", "ind")  # partial


def test_matches_iso2_and_iso3_exactly():
    assert matches_search("India", "in")
    assert matches_search("India", "ind")
    assert matches_search("United States", "us")
    assert matches_search("United States", "usa")


def test_matches_a_colloquial_short_name_that_is_not_the_real_iso_code():
    """"uk" and "uae" are common short names but not the actual ISO-2 code
    (which is GB and AE respectively) -- these must still resolve."""
    assert matches_search("United Kingdom", "uk")
    assert matches_search("United Kingdom", "england")
    assert matches_search("United Arab Emirates", "uae")
    assert matches_search("South Korea", "korea")


def test_matches_calling_code_as_a_substring():
    assert matches_search("India", "91")
    assert matches_search("India", "+91")


def test_does_not_false_positive_across_countries():
    assert not matches_search("India", "us")
    assert not matches_search("India", "uae")
    assert not matches_search("United States", "in")


def test_empty_needle_matches_nothing():
    assert not matches_search("India", "")


def test_provider_short_code_matches_exactly():
    assert matches_search("India", "in", "in")
    assert not matches_search("India", "iny", "in")
