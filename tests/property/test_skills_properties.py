"""Property tests for the skills service (design Properties 5-10)."""

from __future__ import annotations

import string

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.constants import LEVEL_ORDER, LEVELS
from app.exceptions import ConflictError, ValidationError
from app.services.skills_service import SkillsService
from tests.helpers import add_member, make_memory_session

levels = st.sampled_from(LEVELS)
optional_levels = st.one_of(st.none(), levels)
ascii_name = st.text(alphabet=string.ascii_letters + string.digits + " ", min_size=1, max_size=30).filter(
    lambda s: s.strip()
)


def make_service():
    session = make_memory_session()
    return session, SkillsService(session)


# Feature: team-dashboard, Property 5: Skill assignment round-trip
@given(current=levels, aspiration=optional_levels)
@settings(max_examples=100)
def test_skill_assignment_round_trip(current, aspiration):
    session, service = make_service()
    add_member(session)
    skill = service.add_skill("Python")
    service.assign_skill("alice", skill.id, current, aspiration)
    [entry] = service.list_matrix("alice")
    assert entry.current_level == current
    assert entry.aspiration_level == aspiration


# Feature: team-dashboard, Property 6: Invalid proficiency level is rejected
@given(bad_level=st.text(max_size=30).filter(lambda s: s not in LEVELS), original=levels)
@settings(max_examples=100)
def test_invalid_level_rejected(bad_level, original):
    session, service = make_service()
    add_member(session)
    skill = service.add_skill("Python")
    service.assign_skill("alice", skill.id, original)
    with pytest.raises(ValidationError):
        service.assign_skill("alice", skill.id, bad_level)
    [entry] = service.list_matrix("alice")
    assert entry.current_level == original


# Feature: team-dashboard, Property 7: Deprecated skill references are preserved
@given(reference_count=st.integers(min_value=1, max_value=20), level=levels)
@settings(max_examples=100)
def test_deprecated_skill_references_preserved(reference_count, level):
    session, service = make_service()
    skill = service.add_skill("Python")
    for index in range(reference_count):
        add_member(session, username=f"member{index}", name=f"Member {index}")
        service.assign_skill(f"member{index}", skill.id, level)

    result = service.remove_skill(skill.id)
    assert result.deprecated and not result.removed
    assert result.reference_count == reference_count
    for index in range(reference_count):
        [entry] = service.list_matrix(f"member{index}")
        assert entry.skill_deprecated is True
        assert entry.current_level == level


# Feature: team-dashboard, Property 8: Skill name case-insensitive uniqueness
@given(name=ascii_name, variant=st.sampled_from(["upper", "lower", "swapcase", "title"]))
@settings(max_examples=100)
def test_skill_name_case_insensitive_uniqueness(name, variant):
    _, service = make_service()
    service.add_skill(name)
    duplicate = getattr(name, variant)()
    with pytest.raises(ConflictError):
        service.add_skill(duplicate)
    assert len(service.list_catalogue()) == 1


matrix_entries = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=5),  # member index
        st.integers(min_value=0, max_value=3),  # skill index
        levels,
        optional_levels,
    ),
    max_size=25,
)


# Feature: team-dashboard, Property 9: Skills summary aggregation correctness
# Feature: team-dashboard, Property 10: Skills summary reflects latest matrix state
@given(entries=matrix_entries)
@settings(max_examples=100)
def test_summary_aggregation_matches_brute_force(entries):
    session, service = make_service()
    skill_names = ["Python", "Rust", "Go", "SQL"]
    skills = [service.add_skill(name) for name in skill_names]
    for index in range(6):
        add_member(session, username=f"member{index}", name=f"Member {index}")

    # Later assignments overwrite earlier ones (same member+skill), which
    # also exercises Property 10 (summary reflects the latest state).
    final_state: dict[tuple[int, int], tuple[str, str | None]] = {}
    for member_index, skill_index, current, aspiration in entries:
        service.assign_skill(f"member{member_index}", skills[skill_index].id, current, aspiration)
        final_state[(member_index, skill_index)] = (current, aspiration)

    summary = {row.skill_name: row for row in service.get_team_skills_summary()}
    assert set(summary) == set(skill_names)  # every catalogue skill appears

    for skill_index, skill_name in enumerate(skill_names):
        row = summary[skill_name]
        assert set(row.level_counts) == set(LEVELS)  # zero counts included
        for level in LEVELS:
            expected = sum(
                1
                for (_, s_index), (current, _) in final_state.items()
                if s_index == skill_index and current == level
            )
            assert row.level_counts[level] == expected
        expected_aspiring = sum(
            1
            for (_, s_index), (current, aspiration) in final_state.items()
            if s_index == skill_index
            and aspiration is not None
            and LEVEL_ORDER[aspiration] > LEVEL_ORDER[current]
        )
        assert row.aspiration_count == expected_aspiring


import_rows = st.dictionaries(
    keys=st.tuples(
        st.integers(min_value=0, max_value=4),  # member index
        st.integers(min_value=0, max_value=4),  # skill index
    ),
    values=st.tuples(levels, optional_levels),
    min_size=1,
    max_size=15,
)


def rows_to_csv(rows) -> str:
    lines = ["username,skill,current_level,aspiration_level"]
    for (member_index, skill_index), (current, aspiration) in rows.items():
        lines.append(
            f"member{member_index},Skill {skill_index},{current},{aspiration or ''}"
        )
    return "\n".join(lines) + "\n"


def make_import_service(rows):
    session, service = make_service()
    for member_index in {member for member, _ in rows}:
        add_member(session, username=f"member{member_index}", name=f"Member {member_index}")
    return session, service


# Feature: team-dashboard, Property 36: Bulk import round-trip
@given(rows=import_rows)
@settings(max_examples=100)
def test_bulk_import_round_trip(rows):
    _, service = make_import_service(rows)
    result = service.import_matrix_csv(rows_to_csv(rows), create_missing_skills=True)

    assert result.ok
    assert result.imported_count == len(rows)
    assert result.member_count == len({member for member, _ in rows})
    assert sorted(result.created_skills) == sorted(
        {f"Skill {skill}" for _, skill in rows}
    )
    for member_index in {member for member, _ in rows}:
        entries = {
            entry.skill_name: entry for entry in service.list_matrix(f"member{member_index}")
        }
        expected = {
            f"Skill {skill_index}": (current, aspiration)
            for (m_index, skill_index), (current, aspiration) in rows.items()
            if m_index == member_index
        }
        assert set(entries) == set(expected)
        for skill_name, (current, aspiration) in expected.items():
            assert entries[skill_name].current_level == current
            assert entries[skill_name].aspiration_level == aspiration


# Feature: team-dashboard, Property 37: Bulk import atomicity
@given(
    rows=import_rows,
    failure=st.sampled_from(["unknown_username", "bad_level", "duplicate_pair"]),
)
@settings(max_examples=100)
def test_bulk_import_is_atomic(rows, failure):
    _, service = make_import_service(rows)
    csv_text = rows_to_csv(rows)
    (member_index, skill_index), (current, _) = next(iter(rows.items()))
    if failure == "unknown_username":
        csv_text += f"nobody,Skill {skill_index},{current},\n"
    elif failure == "bad_level":
        csv_text += f"member{member_index},Skill {skill_index} b,Wizard,\n"
    else:  # duplicate of an existing row
        csv_text += f"member{member_index},Skill {skill_index},{current},\n"

    result = service.import_matrix_csv(csv_text, create_missing_skills=True)

    assert not result.ok
    assert result.imported_count == 0
    # Nothing was imported and no skills were created, even for valid rows.
    assert service.list_catalogue() == []
    for m_index in {member for member, _ in rows}:
        assert service.list_matrix(f"member{m_index}") == []


# Feature: team-dashboard, Property 38: Missing-skill creation is gated by the option
@given(rows=import_rows)
@settings(max_examples=100)
def test_missing_skill_creation_gated_by_option(rows):
    _, service = make_import_service(rows)
    csv_text = rows_to_csv(rows)

    rejected = service.import_matrix_csv(csv_text, create_missing_skills=False)
    assert not rejected.ok
    assert len(rejected.errors) == len(rows)
    assert all(error.field == "skill" for error in rejected.errors)
    assert service.list_catalogue() == []

    accepted = service.import_matrix_csv(csv_text, create_missing_skills=True)
    assert accepted.ok
    created = sorted(skill.name for skill in service.list_catalogue())
    assert created == sorted({f"Skill {skill}" for _, skill in rows})
