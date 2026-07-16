"""Bulk skills CSV import: service semantics and upload routes
(Requirement 13)."""

from __future__ import annotations

import io

import pytest

from app.constants import MAX_SKILLS_IMPORT_BYTES
from app.exceptions import ValidationError
from app.services.skills_service import SkillsService
from tests.conftest import csrf_for
from tests.helpers import add_member, make_memory_session


@pytest.fixture()
def session():
    return make_memory_session()


@pytest.fixture()
def service(session):
    return SkillsService(session)


def matrix_by_skill(service, username):
    return {entry.skill_name: entry for entry in service.list_matrix(username)}


# -- Service: successful imports ---------------------------------------------


def test_import_creates_and_updates_entries(session, service):
    add_member(session, username="alice")
    add_member(session, username="bob", name="Bob Jones")
    python = service.add_skill("Python")
    service.add_skill("Terraform")
    service.assign_skill("alice", python.id, "Beginner")

    result = service.import_matrix_csv(
        "username,skill,current_level,aspiration_level\n"
        "alice,Python,Advanced,Expert\n"
        "bob,Terraform,Beginner,\n"
        "bob,Python,Intermediate,Advanced\n"
    )

    assert result.ok
    assert result.imported_count == 3
    assert result.member_count == 2
    assert result.created_skills == ()
    alice = matrix_by_skill(service, "alice")
    assert alice["Python"].current_level == "Advanced"
    assert alice["Python"].aspiration_level == "Expert"
    bob = matrix_by_skill(service, "bob")
    assert bob["Terraform"].current_level == "Beginner"
    assert bob["Terraform"].aspiration_level is None
    assert bob["Python"].aspiration_level == "Advanced"


def test_import_header_case_order_and_username_case_insensitive(session, service):
    add_member(session, username="alice")
    service.add_skill("Python")
    result = service.import_matrix_csv(
        "Current_Level,SKILL,Username\nExpert,python,ALICE\n"
    )
    assert result.ok
    assert matrix_by_skill(service, "alice")["Python"].current_level == "Expert"


def test_import_levels_matched_case_insensitively(session, service):
    add_member(session)
    service.add_skill("Python")
    result = service.import_matrix_csv(
        "username,skill,current_level,aspiration_level\nalice,Python,advanced,EXPERT\n"
    )
    assert result.ok
    entry = matrix_by_skill(service, "alice")["Python"]
    assert entry.current_level == "Advanced"
    assert entry.aspiration_level == "Expert"


def test_import_skips_blank_rows_and_ignores_extra_columns(session, service):
    add_member(session)
    service.add_skill("Python")
    result = service.import_matrix_csv(
        "username,skill,current_level,notes\n"
        "\n"
        "alice,Python,Beginner,ignore me\n"
        ",,,\n"
    )
    assert result.ok
    assert result.imported_count == 1


def test_import_creates_missing_skills_when_enabled(session, service):
    add_member(session)
    result = service.import_matrix_csv(
        "username,skill,current_level\nalice,Kubernetes,Beginner\nalice,Go,Expert\n",
        create_missing_skills=True,
    )
    assert result.ok
    assert sorted(result.created_skills) == ["Go", "Kubernetes"]
    assert sorted(skill.name for skill in service.list_catalogue()) == ["Go", "Kubernetes"]


# -- Service: row validation and atomicity -----------------------------------


def test_unknown_username_reports_row_error_and_imports_nothing(session, service):
    add_member(session)
    service.add_skill("Python")
    result = service.import_matrix_csv(
        "username,skill,current_level\n"
        "alice,Python,Beginner\n"
        "charlie,Python,Expert\n"
    )
    assert not result.ok
    assert result.imported_count == 0
    [error] = result.errors
    assert error.row_number == 3
    assert error.field == "username"
    assert "charlie" not in error.message  # never echoes the invalid value
    assert service.list_matrix("alice") == []


def test_unknown_skill_without_create_option_is_an_error(session, service):
    add_member(session)
    result = service.import_matrix_csv(
        "username,skill,current_level\nalice,Kubernetes,Beginner\n"
    )
    assert not result.ok
    [error] = result.errors
    assert (error.row_number, error.field) == (2, "skill")
    assert service.list_catalogue() == []


def test_invalid_levels_reported_without_echoing_value(session, service):
    add_member(session)
    service.add_skill("Python")
    result = service.import_matrix_csv(
        "username,skill,current_level,aspiration_level\nalice,Python,Wizard,Sorcerer\n"
    )
    assert not result.ok
    fields = {error.field for error in result.errors}
    assert fields == {"current_level", "aspiration_level"}
    for error in result.errors:
        assert "Beginner, Intermediate, Advanced, Expert" in error.message
        assert "Wizard" not in error.message
        assert "Sorcerer" not in error.message


def test_duplicate_member_skill_pair_reports_both_rows(session, service):
    add_member(session)
    service.add_skill("Python")
    result = service.import_matrix_csv(
        "username,skill,current_level\n"
        "alice,Python,Beginner\n"
        "ALICE,python,Expert\n"
    )
    assert not result.ok
    [error] = result.errors
    assert error.row_number == 3
    assert "row 2" in error.message
    assert service.list_matrix("alice") == []


def test_failed_import_leaves_existing_entries_and_catalogue_unchanged(session, service):
    add_member(session)
    python = service.add_skill("Python")
    service.assign_skill("alice", python.id, "Beginner")
    result = service.import_matrix_csv(
        "username,skill,current_level\n"
        "alice,Python,Expert\n"
        "alice,NewSkill,Nonsense\n",
        create_missing_skills=True,
    )
    assert not result.ok
    entry = matrix_by_skill(service, "alice")["Python"]
    assert entry.current_level == "Beginner"
    assert [skill.name for skill in service.list_catalogue()] == ["Python"]


def test_missing_username_and_skill_values_are_row_errors(session, service):
    add_member(session)
    service.add_skill("Python")
    result = service.import_matrix_csv(
        "username,skill,current_level\n,Python,Beginner\nalice,,Beginner\n"
    )
    assert not result.ok
    assert {(error.row_number, error.field) for error in result.errors} == {
        (2, "username"),
        (3, "skill"),
    }


# -- Service: file-level validation -------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "username,current_level\nalice,Beginner\n",
        "skill,current_level\nPython,Beginner\n",
        "username,skill,current_level,username\n",
    ],
)
def test_file_level_problems_raise_validation_error(service, text):
    with pytest.raises(ValidationError):
        service.import_matrix_csv(text)


def test_header_only_file_imports_nothing(service):
    result = service.import_matrix_csv("username,skill,current_level\n")
    assert result.ok
    assert result.imported_count == 0


# -- Routes --------------------------------------------------------------------


def upload(client, csv_bytes, filename="skills.csv", create_missing=False, **extra):
    token = csrf_for(client, "/skills/import")
    data = {"csrf_token": token, "file": (io.BytesIO(csv_bytes), filename)}
    if create_missing:
        data["create_missing_skills"] = "1"
    data.update(extra)
    return client.post(
        "/skills/import",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_import_page_requires_authentication(client):
    assert client.get("/skills/import").status_code == 401


def test_import_post_without_csrf_rejected(logged_in_client):
    response = logged_in_client.post(
        "/skills/import",
        data={"file": (io.BytesIO(b"username,skill,current_level\n"), "skills.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_import_flow_end_to_end(logged_in_client):
    token = csrf_for(logged_in_client, "/profiles/new")
    logged_in_client.post(
        "/profiles/new",
        data={"name": "Alice Smith", "username": "alice", "csrf_token": token},
    )
    response = upload(
        logged_in_client,
        b"username,skill,current_level,aspiration_level\nalice,Python,Advanced,Expert\n",
        create_missing=True,
    )
    body = response.get_data(as_text=True)
    assert "Imported 1 skill assignment(s) for 1 team member(s)." in body
    assert "Added 1 new skill(s) to the catalogue." in body

    matrix = logged_in_client.get("/skills/matrix/alice").get_data(as_text=True)
    assert "Python" in matrix
    assert "Advanced" in matrix


def test_import_row_errors_are_listed_on_the_page(logged_in_client):
    response = upload(
        logged_in_client,
        b"username,skill,current_level\nghost,Python,Beginner\n",
        create_missing=True,
    )
    body = response.get_data(as_text=True)
    assert "Nothing was imported" in body
    assert "no team member has this username" in body
    assert "ghost" not in body  # the invalid value is never echoed back


def test_import_rejects_missing_file(logged_in_client):
    token = csrf_for(logged_in_client, "/skills/import")
    response = logged_in_client.post(
        "/skills/import",
        data={"csrf_token": token},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "Choose a CSV file to import." in response.get_data(as_text=True)


def test_import_rejects_oversized_file(logged_in_client):
    big = b"username,skill,current_level\n" + b"x" * MAX_SKILLS_IMPORT_BYTES
    response = upload(logged_in_client, big)
    assert "too large" in response.get_data(as_text=True)


def test_import_rejects_non_utf8_file(logged_in_client):
    response = upload(logged_in_client, b"username,skill,current_level\n\xff\xfe\x9c\n")
    assert "UTF-8" in response.get_data(as_text=True)


def test_import_accepts_utf8_bom(logged_in_client):
    token = csrf_for(logged_in_client, "/profiles/new")
    logged_in_client.post(
        "/profiles/new",
        data={"name": "Alice Smith", "username": "alice", "csrf_token": token},
    )
    csv_with_bom = "\ufeffusername,skill,current_level\nalice,Python,Beginner\n"
    response = upload(logged_in_client, csv_with_bom.encode("utf-8"), create_missing=True)
    assert "Imported 1 skill assignment(s)" in response.get_data(as_text=True)
