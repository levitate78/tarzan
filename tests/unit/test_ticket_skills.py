"""Linking catalogue skills to Jira work items: service behaviour and the
detail-page routes."""

from __future__ import annotations

import pytest

from app.exceptions import NotFoundError
from app.services.cache_service import CacheService
from app.services.jira_service import JiraService
from app.services.skills_service import SkillsService
from tests.conftest import csrf_for
from tests.helpers import FakeJiraClient, make_issue, make_memory_session


@pytest.fixture()
def session():
    return make_memory_session()


def cache_issue(session, key="PROJ-1"):
    service = JiraService(
        session, cache_service=CacheService(session), client=FakeJiraClient([make_issue(key)])
    )
    assert service.fetch_and_cache("PROJ").success


def test_assign_list_and_remove_ticket_skill(session):
    cache_issue(session)
    skills = SkillsService(session)
    python = skills.add_skill("Python")
    flask = skills.add_skill("Flask")

    skills.assign_ticket_skill("PROJ-1", python.id)
    skills.assign_ticket_skill("PROJ-1", flask.id)
    assert [s.name for s in skills.list_ticket_skills("PROJ-1")] == ["Flask", "Python"]

    skills.remove_ticket_skill("PROJ-1", flask.id)
    assert [s.name for s in skills.list_ticket_skills("PROJ-1")] == ["Python"]


def test_assign_ticket_skill_is_idempotent(session):
    cache_issue(session)
    skills = SkillsService(session)
    python = skills.add_skill("Python")
    skills.assign_ticket_skill("PROJ-1", python.id)
    skills.assign_ticket_skill("PROJ-1", python.id)
    assert len(skills.list_ticket_skills("PROJ-1")) == 1


def test_assign_ticket_skill_requires_cached_work_item_and_skill(session):
    skills = SkillsService(session)
    python = skills.add_skill("Python")
    with pytest.raises(NotFoundError):
        skills.assign_ticket_skill("PROJ-404", python.id)
    cache_issue(session)
    with pytest.raises(NotFoundError):
        skills.assign_ticket_skill("PROJ-1", 999)


def test_remove_unlinked_ticket_skill_raises(session):
    cache_issue(session)
    skills = SkillsService(session)
    python = skills.add_skill("Python")
    with pytest.raises(NotFoundError):
        skills.remove_ticket_skill("PROJ-1", python.id)


def test_ticket_skill_links_survive_cache_refresh(session):
    cache_issue(session)
    skills = SkillsService(session)
    python = skills.add_skill("Python")
    skills.assign_ticket_skill("PROJ-1", python.id)

    cache_issue(session)  # refresh recreates/updates the work item row
    assert [s.name for s in skills.list_ticket_skills("PROJ-1")] == ["Python"]


# -- Routes ------------------------------------------------------------------


def seed(app):
    session = app.extensions["tarzan_session_factory"]()
    try:
        cache_issue(session)
        skill = SkillsService(session).add_skill("Python")
        return skill.id
    finally:
        session.close()


def test_link_and_unlink_skill_via_detail_page(app, logged_in_client):
    skill_id = seed(app)
    token = csrf_for(logged_in_client, "/jira/PROJ-1")
    response = logged_in_client.post(
        "/jira/PROJ-1/skills",
        data={"skill_id": str(skill_id), "csrf_token": token},
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)
    assert "Linked skill Python to PROJ-1." in page
    assert 'class="badge skill-badge"' in page

    token = csrf_for(logged_in_client, "/jira/PROJ-1")
    response = logged_in_client.post(
        f"/jira/PROJ-1/skills/{skill_id}/remove",
        data={"csrf_token": token},
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)
    assert "Removed skill Python from PROJ-1." in page
    assert 'class="badge skill-badge"' not in page


def test_link_skill_rejects_invalid_skill_id(app, logged_in_client):
    seed(app)
    token = csrf_for(logged_in_client, "/jira/PROJ-1")
    response = logged_in_client.post(
        "/jira/PROJ-1/skills",
        data={"skill_id": "not-a-number", "csrf_token": token},
        follow_redirects=True,
    )
    assert "Choose a skill from the catalogue" in response.get_data(as_text=True)
