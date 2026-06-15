from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DB
from app.models import GitLabMR, MRIssueLink
from app.schemas import GitLabMRResponse, PaginatedResponse

router = APIRouter(prefix="/merge-requests", tags=["GitLab"])


def _mr_query():
    return select(GitLabMR).options(
        selectinload(GitLabMR.issue_links).selectinload(MRIssueLink.issue)
    )


@router.get("", response_model=PaginatedResponse)
async def list_mrs(
    db: DB,
    _: CurrentUser,
    author: Optional[str] = Query(None),
    reviewer: Optional[str] = Query(None),
    mr_state: Optional[str] = Query(None, alias="state"),
    breached_only: bool = Query(False),
    user_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedResponse:
    from sqlalchemy import and_, or_
    from app.models import User

    q = _mr_query()
    filters = []

    if mr_state:
        filters.append(GitLabMR.state == mr_state)
    else:
        filters.append(GitLabMR.state == "opened")

    if breached_only:
        filters.append(GitLabMR.breached == True)

    if author:
        filters.append(GitLabMR.author_username == author)

    # reviewer filter (array contains)
    if reviewer:
        filters.append(GitLabMR.reviewer_usernames.any(reviewer))

    # user_id: match author or reviewer by gitlab_username
    if user_id:
        user_res = await db.execute(select(User).where(User.id == user_id))
        user = user_res.scalar_one_or_none()
        if user and user.gitlab_username:
            filters.append(
                or_(
                    GitLabMR.author_username == user.gitlab_username,
                    GitLabMR.reviewer_usernames.any(user.gitlab_username),
                    GitLabMR.assignee_usernames.any(user.gitlab_username),
                )
            )

    if filters:
        q = q.where(and_(*filters))

    count_q = select(func.count()).select_from(GitLabMR)
    if filters:
        count_q = count_q.where(and_(*filters))

    total = (await db.execute(count_q)).scalar_one()
    result = await db.execute(
        q.order_by(GitLabMR.mr_created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    mrs = result.scalars().unique().all()
    return PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[GitLabMRResponse.model_validate(mr) for mr in mrs],
    )


@router.get("/{mr_id}", response_model=GitLabMRResponse)
async def get_mr(mr_id: str, db: DB, _: CurrentUser) -> GitLabMRResponse:
    result = await db.execute(_mr_query().where(GitLabMR.id == mr_id))
    mr = result.scalar_one_or_none()
    if not mr:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Merge request not found")
    return GitLabMRResponse.model_validate(mr)
