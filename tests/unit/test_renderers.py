"""Template rendering tests for the shared card partials and accessibility
invariants (Requirements 4.3-4.5, 6.3-6.4, 7.2, 11.6)."""

from __future__ import annotations

import re
from datetime import timedelta

from app.dtos import MergeRequestDTO, TicketLinkDTO, WorkItemDTO
from app.util import utcnow
from tests.conftest import csrf_for


def render_work_item(app, item: WorkItemDTO) -> str:
    with app.test_request_context():
        return app.jinja_env.get_template("partials/_work_item_card.html").render(item=item)


def render_mr(app, mr: MergeRequestDTO) -> str:
    with app.test_request_context():
        return app.jinja_env.get_template("partials/_mr_card.html").render(mr=mr)


def make_item(**overrides) -> WorkItemDTO:
    values = dict(
        issue_key="PROJ-1",
        summary="Fix the login flow",
        assignee_account_id="acc-1",
        assignee_display_name="Alice Smith",
        status="In Progress",
        priority="High",
        is_blocked=False,
        is_in_review=False,
    )
    values.update(overrides)
    return WorkItemDTO(**values)


def make_mr_dto(**overrides) -> MergeRequestDTO:
    values = dict(
        gitlab_id=101,
        project_id=1,
        title="Add search endpoint",
        author_username="alice",
        target_branch="main",
        source_branch="feature/search",
        review_status="Awaiting Review",
        created_at=utcnow() - timedelta(days=1),
        web_url="https://gitlab.example.com/mr/101",
        reviewers=("bob",),
        ticket_links=(),
        overdue=False,
    )
    values.update(overrides)
    return MergeRequestDTO(**values)


def test_work_item_card_contains_required_fields(app):
    html = render_work_item(app, make_item())
    for value in ["PROJ-1", "Fix the login flow", "Alice Smith", "In Progress", "High"]:
        assert value in html


def test_blocked_indicator_present_and_distinct(app):
    html = render_work_item(app, make_item(is_blocked=True))
    assert "badge-blocked" in html
    assert "badge-in-review" not in html


def test_in_review_indicator_present_and_distinct(app):
    html = render_work_item(app, make_item(is_in_review=True))
    assert "badge-in-review" in html
    assert "badge-blocked" not in html


def test_no_indicators_when_neither_condition(app):
    html = render_work_item(app, make_item())
    assert "badge-blocked" not in html
    assert "badge-in-review" not in html


def test_mr_card_contains_required_fields(app):
    mr = make_mr_dto()
    html = render_mr(app, mr)
    for value in ["Add search endpoint", "alice", "main", "Awaiting Review"]:
        assert value in html
    assert mr.created_at.strftime("%Y-%m-%d %H:%M") in html


def test_mr_overdue_indicator(app):
    assert "mr-overdue" in render_mr(app, make_mr_dto(overdue=True))
    assert "mr-overdue" not in render_mr(app, make_mr_dto(overdue=False))


def test_mr_ticket_links_rendered(app):
    mr = make_mr_dto(
        ticket_links=(
            TicketLinkDTO("PROJ-1", True, "https://jira.example.com/browse/PROJ-1"),
            TicketLinkDTO("PROJ-2", False, None),
        )
    )
    html = render_mr(app, mr)
    assert '<a class="ticket-ref" href="https://jira.example.com/browse/PROJ-1"' in html
    assert "ticket-ref-unavailable" in html
    assert "PROJ-2" in html


def test_review_status_badge_variants(app):
    for status in ("Awaiting Review", "Changes Requested", "Approved"):
        html = render_mr(app, make_mr_dto(review_status=status))
        assert status in html


IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
ALT_ATTR = re.compile(r'alt="([^"]*)"')


def test_all_images_have_alt_text_within_limit(logged_in_client, app, tmp_path):
    # Create a member with an avatar so an <img> is rendered.
    token = csrf_for(logged_in_client, "/profiles/new")
    logged_in_client.post(
        "/profiles/new",
        data={"name": "Alice Smith", "username": "alice", "csrf_token": token},
    )
    from app.blueprints.common import profile_service

    with app.test_request_context():
        profile_service().save_avatar("alice", b"\x89PNG fake", "image/png")

    for route in ["/profiles/", "/profiles/alice", "/jira/", "/gitlab/", "/skills/dashboard"]:
        body = logged_in_client.get(route).get_data(as_text=True)
        for img in IMG_TAG.findall(body):
            match = ALT_ATTR.search(img)
            assert match, f"<img> without alt on {route}: {img}"
            assert 0 < len(match.group(1)) <= 125, f"alt length out of range on {route}"
