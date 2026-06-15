from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DB, require_role, write_audit_log
from app.core.rbac import Role
from app.models import ConnectorConfig, JiraIssue, MRIssueLink, User
from app.schemas import IssueReassignRequest, JiraIssueResponse, PaginatedResponse

router = APIRouter(prefix="/issues", tags=["Jira"])


def _issue_query():
    return select(JiraIssue).options(
        selectinload(JiraIssue.assignee),
        selectinload(JiraIssue.mr_links).selectinload(MRIssueLink.mr),
    )


@router.get("", response_model=PaginatedResponse)
async def list_issues(
    db: DB,
    _: CurrentUser,
    assignee_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    project_key: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedResponse:
    q = _issue_query()
    if assignee_id:
        q = q.where(JiraIssue.assignee_id == assignee_id)
    if status:
        q = q.where(JiraIssue.status == status)
    if project_key:
        q = q.where(JiraIssue.project_key == project_key)

    count_q = select(func.count()).select_from(JiraIssue)
    if assignee_id:
        count_q = count_q.where(JiraIssue.assignee_id == assignee_id)
    if status:
        count_q = count_q.where(JiraIssue.status == status)
    if project_key:
        count_q = count_q.where(JiraIssue.project_key == project_key)

    total_res = await db.execute(count_q)
    total = total_res.scalar_one()

    result = await db.execute(
        q.order_by(JiraIssue.jira_updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    issues = result.scalars().unique().all()
    return PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[JiraIssueResponse.model_validate(i) for i in issues],
    )


@router.get("/{issue_id}", response_model=JiraIssueResponse)
async def get_issue(issue_id: str, db: DB, _: CurrentUser) -> JiraIssueResponse:
    result = await db.execute(_issue_query().where(JiraIssue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Issue not found")
    return JiraIssueResponse.model_validate(issue)


@router.post("/{issue_id}/reassign", response_model=JiraIssueResponse,
             dependencies=[require_role(Role.lead)])
async def reassign_issue(
    issue_id: str,
    body: IssueReassignRequest,
    db: DB,
    current_user: CurrentUser,
) -> JiraIssueResponse:
    """Reassign a Jira issue via the Jira API and update local cache."""
    from app.connectors.jira import JiraConnector

    result = await db.execute(_issue_query().where(JiraIssue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Issue not found")

    # Load Jira connector config
    config_res = await db.execute(
        select(ConnectorConfig).where(ConnectorConfig.connector_type == "jira")
    )
    config = config_res.scalar_one_or_none()
    if not config:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Jira connector not configured")

    connector = JiraConnector(base_url=config.base_url, token=config.token)
    try:
        await connector.reassign_issue(issue.key, body.assignee_username)
    finally:
        await connector.close()

    # Update local user mapping
    user_res = await db.execute(
        select(User).where(User.jira_username == body.assignee_username)
    )
    new_assignee = user_res.scalar_one_or_none()
    issue.assignee_id = new_assignee.id if new_assignee else None

    await db.commit()
    await write_audit_log(
        db, current_user.id, "reassign_issue", "jira_issue", issue_id,
        f"Reassigned to {body.assignee_username}"
    )
    await db.commit()

    result = await db.execute(_issue_query().where(JiraIssue.id == issue_id))
    return JiraIssueResponse.model_validate(result.scalar_one())
