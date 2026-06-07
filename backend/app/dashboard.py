from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DB
from app.models import GitLabMR, JiraIssue, User
from app.schemas import MemberSummary, TeamDashboard, UserSummary

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


async def _member_summary(user: User, db) -> MemberSummary:
    open_issues = (
        await db.execute(
            select(func.count()).select_from(JiraIssue).where(
                JiraIssue.assignee_id == user.id,
                JiraIssue.status.not_in(["done", "cancelled"]),
            )
        )
    ).scalar_one()

    blocked = (
        await db.execute(
            select(func.count()).select_from(JiraIssue).where(
                JiraIssue.assignee_id == user.id,
                JiraIssue.status == "blocked",
            )
        )
    ).scalar_one()

    gl_user = user.gitlab_username
    open_mrs = breached_mrs = 0
    if gl_user:
        from sqlalchemy import or_
        mr_filter = or_(
            GitLabMR.author_username == gl_user,
            GitLabMR.reviewer_usernames.any(gl_user),
            GitLabMR.assignee_usernames.any(gl_user),
        )
        open_mrs = (
            await db.execute(
                select(func.count()).select_from(GitLabMR).where(
                    GitLabMR.state == "opened", mr_filter
                )
            )
        ).scalar_one()

        breached_mrs = (
            await db.execute(
                select(func.count()).select_from(GitLabMR).where(
                    GitLabMR.state == "opened",
                    GitLabMR.breached == True,
                    mr_filter,
                )
            )
        ).scalar_one()

    return MemberSummary(
        user=UserSummary.model_validate(user),
        open_issues=open_issues,
        blocked_issues=blocked,
        open_mrs=open_mrs,
        breached_mrs=breached_mrs,
    )


@router.get("/team", response_model=TeamDashboard)
async def team_dashboard(db: DB, _: CurrentUser) -> TeamDashboard:
    users_res = await db.execute(select(User).where(User.is_active == True))
    users = users_res.scalars().all()

    total_open_issues = (
        await db.execute(
            select(func.count()).select_from(JiraIssue).where(
                JiraIssue.status.not_in(["done", "cancelled"])
            )
        )
    ).scalar_one()

    total_open_mrs = (
        await db.execute(
            select(func.count()).select_from(GitLabMR).where(GitLabMR.state == "opened")
        )
    ).scalar_one()

    mrs_breached = (
        await db.execute(
            select(func.count()).select_from(GitLabMR).where(
                GitLabMR.state == "opened", GitLabMR.breached == True
            )
        )
    ).scalar_one()

    # Issues by status
    status_rows = await db.execute(
        select(JiraIssue.status, func.count()).group_by(JiraIssue.status)
    )
    issues_by_status = {row[0]: row[1] for row in status_rows.all()}

    members = [await _member_summary(u, db) for u in users]

    return TeamDashboard(
        total_members=len(users),
        total_open_issues=total_open_issues,
        total_open_mrs=total_open_mrs,
        issues_by_status=issues_by_status,
        mrs_breached=mrs_breached,
        members=members,
    )


@router.get("/member/{user_id}", response_model=MemberSummary)
async def member_dashboard(user_id: str, db: DB, _: CurrentUser) -> MemberSummary:
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return await _member_summary(user, db)