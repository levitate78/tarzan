from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DB, require_role, write_audit_log
from app.core.rbac import Role
from app.core.security import hash_password
from app.models import Skill, SkillLevel, User
from app.schemas import (
    PaginatedResponse,
    SkillLevelResponse,
    SkillLevelSet,
    UserCreate,
    UserResponse,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["Users"])


def _user_query():
    return select(User).options(
        selectinload(User.skill_levels).selectinload(SkillLevel.skill)
    )


@router.get("", response_model=PaginatedResponse)
async def list_users(
    db: DB,
    _: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse:
    total_q = await db.execute(select(func.count()).select_from(User).where(User.is_active == True))
    total = total_q.scalar_one()

    result = await db.execute(
        _user_query()
        .where(User.is_active == True)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    users = result.scalars().unique().all()
    return PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[UserResponse.model_validate(u) for u in users],
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[require_role(Role.admin)])
async def create_user(body: UserCreate, db: DB, current_user: CurrentUser) -> UserResponse:
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")

    user = User(
        username=body.username,
        email=body.email,
        full_name=body.full_name,
        avatar_url=body.avatar_url,
        gitlab_username=body.gitlab_username,
        jira_username=body.jira_username,
        role=body.role.value,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await write_audit_log(db, current_user.id, "create_user", "user", user.id)
    await db.commit()

    result = await db.execute(_user_query().where(User.id == user.id))
    return UserResponse.model_validate(result.scalar_one())


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, db: DB, _: CurrentUser) -> UserResponse:
    result = await db.execute(_user_query().where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UserUpdate,
    db: DB,
    current_user: CurrentUser,
) -> UserResponse:
    # Only admins or the user themselves can update
    from app.core.rbac import can_admin
    if current_user.id != user_id and not can_admin(current_user.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot modify another user's profile")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    for field, val in body.model_dump(exclude_none=True).items():
        setattr(user, field, val.value if hasattr(val, "value") else val)

    await db.commit()
    await write_audit_log(db, current_user.id, "update_user", "user", user_id)
    await db.commit()

    result = await db.execute(_user_query().where(User.id == user_id))
    return UserResponse.model_validate(result.scalar_one())


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[require_role(Role.admin)])
async def deactivate_user(user_id: str, db: DB, current_user: CurrentUser) -> None:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.is_active = False
    await db.commit()
    await write_audit_log(db, current_user.id, "deactivate_user", "user", user_id)
    await db.commit()


@router.put("/{user_id}/skills", response_model=list[SkillLevelResponse])
async def set_user_skills(
    user_id: str,
    body: list[SkillLevelSet],
    db: DB,
    current_user: CurrentUser,
) -> list[SkillLevelResponse]:
    from app.core.rbac import can_admin
    if current_user.id != user_id and not can_admin(current_user.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot modify another user's skills")

    result = await db.execute(select(User).where(User.id == user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # Upsert skill levels
    for item in body:
        existing = await db.execute(
            select(SkillLevel).where(
                SkillLevel.user_id == user_id, SkillLevel.skill_id == item.skill_id
            )
        )
        sl = existing.scalar_one_or_none()
        if sl:
            sl.level = item.level
            sl.aspiration_level = item.aspiration_level
        else:
            sl = SkillLevel(
                user_id=user_id,
                skill_id=item.skill_id,
                level=item.level,
                aspiration_level=item.aspiration_level,
            )
            db.add(sl)

    await db.commit()

    result = await db.execute(
        select(SkillLevel)
        .options(selectinload(SkillLevel.skill))
        .where(SkillLevel.user_id == user_id)
    )
    return [SkillLevelResponse.model_validate(sl) for sl in result.scalars().all()]