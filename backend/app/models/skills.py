from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DB, require_role
from app.core.rbac import Role
from app.models import Skill, SkillLevel
from app.schemas import SkillCategory, SkillCreate, SkillResponse, TeamSkillsMatrix

router = APIRouter(prefix="/skills", tags=["Skills"])


@router.get("", response_model=list[SkillResponse])
async def list_skills(
    db: DB,
    _: CurrentUser,
    category: Optional[str] = Query(None),
) -> list[SkillResponse]:
    q = select(Skill)
    if category:
        q = q.where(Skill.category == category)
    result = await db.execute(q.order_by(Skill.category, Skill.name))
    return [SkillResponse.model_validate(s) for s in result.scalars().all()]


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[require_role(Role.admin)])
async def create_skill(body: SkillCreate, db: DB, _: CurrentUser) -> SkillResponse:
    existing = await db.execute(select(Skill).where(Skill.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Skill name already exists")

    skill = Skill(name=body.name, category=body.category.value, description=body.description)
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return SkillResponse.model_validate(skill)


@router.get("/matrix", response_model=list[TeamSkillsMatrix])
async def skill_matrix(db: DB, _: CurrentUser) -> list[TeamSkillsMatrix]:
    """Return aggregated skill data across all active team members."""
    skills_res = await db.execute(
        select(Skill).options(selectinload(Skill.levels).selectinload(SkillLevel.user))
    )
    skills = skills_res.scalars().all()

    matrix = []
    for skill in skills:
        active_levels = [sl for sl in skill.levels if sl.user and sl.user.is_active]
        if not active_levels:
            continue

        dist: dict[str, int] = {str(i): 0 for i in range(6)}
        total = 0
        gap_count = 0
        for sl in active_levels:
            dist[str(sl.level)] = dist.get(str(sl.level), 0) + 1
            total += sl.level
            if sl.aspiration_level and sl.aspiration_level > sl.level:
                gap_count += 1

        matrix.append(
            TeamSkillsMatrix(
                skill=SkillResponse.model_validate(skill),
                member_count=len(active_levels),
                average_level=total / len(active_levels),
                gap_count=gap_count,
                distribution=dist,
            )
        )
    return matrix


@router.patch("/{skill_id}", response_model=SkillResponse,
              dependencies=[require_role(Role.admin)])
async def update_skill(skill_id: str, body: SkillCreate, db: DB, _: CurrentUser) -> SkillResponse:
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill not found")

    skill.name = body.name
    skill.category = body.category.value
    skill.description = body.description
    await db.commit()
    await db.refresh(skill)
    return SkillResponse.model_validate(skill)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[require_role(Role.admin)])
async def delete_skill(skill_id: str, db: DB, _: CurrentUser) -> None:
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill not found")
    await db.delete(skill)
    await db.commit()