import pytest

from app.constants import LEVELS
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.services.skills_service import SkillsService
from tests.helpers import add_member, make_memory_session


@pytest.fixture()
def session():
    return make_memory_session()


@pytest.fixture()
def service(session):
    return SkillsService(session)


def test_add_and_list_skills(service):
    service.add_skill("Python")
    service.add_skill("Terraform")
    names = [skill.name for skill in service.list_catalogue()]
    assert names == ["Python", "Terraform"]


def test_duplicate_skill_name_case_insensitive(service):
    service.add_skill("Python")
    for variant in ("python", "PYTHON", " Python "):
        with pytest.raises(ConflictError):
            service.add_skill(variant)
    assert len(service.list_catalogue()) == 1


def test_empty_skill_name_rejected(service):
    with pytest.raises(ValidationError):
        service.add_skill("   ")


def test_assign_skill_round_trip(session, service):
    add_member(session)
    skill = service.add_skill("Python")
    service.assign_skill("alice", skill.id, "Advanced", "Expert")
    [entry] = service.list_matrix("alice")
    assert entry.current_level == "Advanced"
    assert entry.aspiration_level == "Expert"


def test_invalid_level_rejected_and_entry_unchanged(session, service):
    add_member(session)
    skill = service.add_skill("Python")
    service.assign_skill("alice", skill.id, "Beginner")
    with pytest.raises(ValidationError):
        service.assign_skill("alice", skill.id, "Wizard")
    [entry] = service.list_matrix("alice")
    assert entry.current_level == "Beginner"


def test_remove_unreferenced_skill_deletes(service):
    skill = service.add_skill("Python")
    result = service.remove_skill(skill.id)
    assert result.removed and not result.deprecated
    assert service.list_catalogue() == []


def test_remove_referenced_skill_deprecates_and_keeps_entries(session, service):
    add_member(session)
    skill = service.add_skill("Python")
    service.assign_skill("alice", skill.id, "Expert")
    result = service.remove_skill(skill.id)
    assert not result.removed and result.deprecated
    assert result.reference_count == 1
    [entry] = service.list_matrix("alice")
    assert entry.skill_deprecated is True
    assert entry.current_level == "Expert"


def test_remove_matrix_entry(session, service):
    add_member(session)
    skill = service.add_skill("Python")
    service.assign_skill("alice", skill.id, "Beginner")
    service.remove_matrix_entry("alice", skill.id)
    assert service.list_matrix("alice") == []
    with pytest.raises(NotFoundError):
        service.remove_matrix_entry("alice", skill.id)


def test_summary_includes_zero_counts_and_aspirations(session, service):
    add_member(session, username="alice", name="Alice")
    add_member(session, username="bob", name="Bob")
    python = service.add_skill("Python")
    service.add_skill("Rust")
    service.assign_skill("alice", python.id, "Advanced", "Expert")
    service.assign_skill("bob", python.id, "Beginner", "Beginner")

    summary = {row.skill_name: row for row in service.get_team_skills_summary()}
    assert set(summary) == {"Python", "Rust"}
    python_row = summary["Python"]
    assert python_row.level_counts == {
        "Beginner": 1,
        "Intermediate": 0,
        "Advanced": 1,
        "Expert": 0,
    }
    assert python_row.aspiration_count == 1  # only Alice aspires higher
    rust_row = summary["Rust"]
    assert all(rust_row.level_counts[level] == 0 for level in LEVELS)
    assert rust_row.aspiration_count == 0


def test_summary_reflects_latest_update(session, service):
    add_member(session)
    skill = service.add_skill("Python")
    service.assign_skill("alice", skill.id, "Beginner")
    service.assign_skill("alice", skill.id, "Expert")
    [row] = service.get_team_skills_summary()
    assert row.level_counts["Expert"] == 1
    assert row.level_counts["Beginner"] == 0
