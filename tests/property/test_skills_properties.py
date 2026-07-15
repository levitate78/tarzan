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
