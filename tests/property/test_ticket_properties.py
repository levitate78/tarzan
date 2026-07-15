"""Property tests for ticket reference extraction (design Properties 23-24)."""

from __future__ import annotations

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from app.ticket_linking import extract_ticket_references

CONFIGURED_KEYS = {"PROJ", "ABC", "TARZAN"}
UNCONFIGURED_KEYS = ["XYZ", "OTHER", "QQ"]

configured_ref = st.builds(
    lambda key, number: f"{key}-{number}",
    st.sampled_from(sorted(CONFIGURED_KEYS)),
    st.integers(min_value=0, max_value=999_999),
)
unconfigured_ref = st.builds(
    lambda key, number: f"{key}-{number}",
    st.sampled_from(UNCONFIGURED_KEYS),
    st.integers(min_value=0, max_value=999_999),
)
# Noise tokens contain no uppercase letters, so they can never form a
# reference or merge with one across the space separator.
noise = st.text(alphabet=string.ascii_lowercase + string.punctuation.replace("-", ""), max_size=10)

token = st.one_of(
    st.tuples(st.just("valid"), configured_ref),
    st.tuples(st.just("invalid"), unconfigured_ref),
    st.tuples(st.just("noise"), noise),
)


# Feature: team-dashboard, Property 23: Ticket reference extraction correctness
@given(tokens=st.lists(token, max_size=15))
@settings(max_examples=100)
def test_extraction_returns_exactly_configured_references(tokens):
    text = " ".join(value for _, value in tokens)
    expected = {value for kind, value in tokens if kind == "valid"}
    assert extract_ticket_references(text, CONFIGURED_KEYS) == expected


# Feature: team-dashboard, Property 23 (no-match case)
@given(text=st.text(alphabet=string.ascii_lowercase + string.digits + " .,!?", max_size=200))
@settings(max_examples=100)
def test_text_without_references_returns_empty_set(text):
    assert extract_ticket_references(text, CONFIGURED_KEYS) == set()


# Feature: team-dashboard, Property 24: Ticket reference deduplication
@given(reference=configured_ref, repeats=st.integers(min_value=2, max_value=10))
@settings(max_examples=100)
def test_repeated_reference_deduplicated(reference, repeats):
    text = " fix for ".join([reference] * repeats)
    assert extract_ticket_references(text, CONFIGURED_KEYS) == {reference}
