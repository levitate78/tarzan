"""Unit tests for the bulk skill-import CSV parser (app.skills_csv).

Pure parsing/validation — no database or FastAPI app required.
"""

from __future__ import annotations

import pytest

from app.skills_csv import MAX_ROWS, SkillsCsvError, parse_skills_csv


def test_parses_valid_rows():
    result = parse_skills_csv(
        "username,skill,level,aspiration_level,category\n"
        "alice,Python,4,5,languages\n"
        "bob,Terraform,2,,devops\n"
    )
    assert result.errors == []
    assert len(result.rows) == 2

    first, second = result.rows
    assert (first.line, first.username, first.skill_name) == (2, "alice", "Python")
    assert (first.level, first.aspiration_level, first.category) == (4, 5, "languages")
    assert second.aspiration_level is None


def test_optional_columns_can_be_omitted():
    result = parse_skills_csv("username,skill,level\nalice,Python,3\n")
    assert result.errors == []
    row = result.rows[0]
    assert row.aspiration_level is None
    assert row.category is None


def test_header_is_case_insensitive_and_order_free():
    result = parse_skills_csv("Level,SKILL,Username\n3,Python,alice\n")
    assert result.errors == []
    assert result.rows[0].username == "alice"
    assert result.rows[0].level == 3


def test_empty_content_raises():
    with pytest.raises(SkillsCsvError, match="empty"):
        parse_skills_csv("")


def test_missing_required_column_raises():
    with pytest.raises(SkillsCsvError, match="level"):
        parse_skills_csv("username,skill\nalice,Python\n")


def test_duplicate_header_column_raises():
    with pytest.raises(SkillsCsvError, match="duplicate"):
        parse_skills_csv("username,skill,level,level\nalice,Python,3,4\n")


@pytest.mark.parametrize(
    ("row", "message_fragment"),
    [
        (",Python,3", "'username' is required"),
        ("alice,,3", "'skill' is required"),
        ("alice,Python,", "'level' is required"),
        ("alice,Python,abc", "must be an integer"),
        ("alice,Python,guru", "must be an integer"),
        ("alice,Python,6", "between 0 and 5"),
        ("alice,Python,-1", "between 0 and 5"),
    ],
)
def test_invalid_rows_are_reported_not_fatal(row: str, message_fragment: str):
    result = parse_skills_csv(f"username,skill,level\n{row}\nbob,Go,2\n")
    assert len(result.rows) == 1  # the valid bob row still parses
    assert len(result.errors) == 1
    line, message = result.errors[0]
    assert line == 2
    assert message_fragment in message


def test_invalid_aspiration_level_is_reported():
    result = parse_skills_csv(
        "username,skill,level,aspiration_level\nalice,Python,3,9\n"
    )
    assert result.rows == []
    assert "aspiration_level" in result.errors[0][1]


def test_unknown_category_is_reported_without_echoing_value():
    result = parse_skills_csv(
        "username,skill,level,category\nalice,Python,3,wizardry\n"
    )
    assert result.rows == []
    assert "unknown category" in result.errors[0][1]
    # Spec (Req 10.3): validation errors must not echo the invalid value back.
    assert "wizardry" not in result.errors[0][1]


def test_named_levels_map_to_numeric_scale():
    result = parse_skills_csv(
        "username,skill,level,aspiration_level\n"
        "alice,Python,Beginner,EXPERT\n"
        "bob,Go,intermediate,\n"
        "carol,Rust,none,advanced\n"
    )
    assert result.errors == []
    assert [(r.level, r.aspiration_level) for r in result.rows] == [(1, 5), (3, None), (0, 4)]


def test_duplicate_user_skill_rows_are_reported():
    result = parse_skills_csv(
        "username,skill,level\nalice,Python,3\nalice,python,5\n"
    )
    assert len(result.rows) == 1
    assert result.rows[0].level == 3
    assert "duplicate" in result.errors[0][1]


def test_blank_lines_are_skipped():
    result = parse_skills_csv("username,skill,level\n\nalice,Python,3\n,,\n")
    assert result.errors == []
    assert len(result.rows) == 1


def test_values_are_whitespace_trimmed():
    result = parse_skills_csv("username,skill,level\n  alice , Python , 3 \n")
    assert result.errors == []
    assert result.rows[0].username == "alice"
    assert result.rows[0].skill_name == "Python"


def test_row_cap_is_enforced():
    lines = "\n".join(f"user{i},Python,3" for i in range(MAX_ROWS + 1))
    result = parse_skills_csv(f"username,skill,level\n{lines}\n")
    assert len(result.rows) == MAX_ROWS
    assert len(result.errors) == 1
    assert "limited to" in result.errors[0][1]
