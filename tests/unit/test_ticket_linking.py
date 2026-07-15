from app.ticket_linking import extract_ticket_references

KEYS = {"PROJ", "ABC"}


def test_extracts_reference_from_text():
    assert extract_ticket_references("Fix PROJ-123 login", KEYS) == {"PROJ-123"}


def test_multiple_distinct_references():
    text = "PROJ-1 and ABC-22 and PROJ-333"
    assert extract_ticket_references(text, KEYS) == {"PROJ-1", "ABC-22", "PROJ-333"}


def test_duplicates_deduplicated():
    assert extract_ticket_references("ABC-123 fix for ABC-123", KEYS) == {"ABC-123"}


def test_unconfigured_project_prefix_ignored():
    assert extract_ticket_references("OTHER-123", KEYS) == set()


def test_prefix_must_match_whole_key():
    # XPROJ is not a configured key; the match must not be split into PROJ-1.
    assert extract_ticket_references("XPROJ-1", KEYS) == set()


def test_more_than_six_digits_rejected():
    assert extract_ticket_references("PROJ-1234567", KEYS) == set()


def test_six_digits_accepted():
    assert extract_ticket_references("PROJ-123456", KEYS) == {"PROJ-123456"}


def test_empty_and_no_match_return_empty_set():
    assert extract_ticket_references("", KEYS) == set()
    assert extract_ticket_references(None, KEYS) == set()
    assert extract_ticket_references("no tickets here", KEYS) == set()
    assert extract_ticket_references("PROJ-1", set()) == set()


def test_branch_name_style():
    assert extract_ticket_references("feature/PROJ-42-add-login", KEYS) == {"PROJ-42"}
