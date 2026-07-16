"""Bulk import of team member skill levels from a CSV file (admin only).

Additive router alongside the existing ``/skills`` endpoints: accepts the
CSV content as text, upserts skill levels per (user, skill), and optionally
creates missing catalogue skills when the row provides a category. Valid
rows are applied; invalid rows are skipped and reported back per line, so
an admin can fix and re-import (the upsert makes re-imports idempotent).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DB, require_role, write_audit_log
from app.core.rbac import Role
from app.models import Skill, SkillLevel, User
from app.schemas import (
    SkillsImportRequest,
    SkillsImportResult,
    SkillsImportRowError,
)
from app.skills_csv import SkillsCsvError, parse_skills_csv

router = APIRouter(prefix="/skills", tags=["Skills"])


@router.post("/import", response_model=SkillsImportResult,
             dependencies=[require_role(Role.admin)])
async def import_skill_levels(
    body: SkillsImportRequest,
    db: DB,
    current_user: CurrentUser,
) -> SkillsImportResult:
    """Bulk import skill levels for team members from CSV content."""
    try:
        parsed = parse_skills_csv(body.csv_content)
    except SkillsCsvError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None

    errors = [SkillsImportRowError(line=line, message=message) for line, message in parsed.errors]

    usernames = {row.username for row in parsed.rows}
    users_result = await db.execute(select(User).where(User.username.in_(usernames)))
    users_by_username = {user.username: user for user in users_result.scalars().all()}

    skills_result = await db.execute(select(Skill))
    skills_by_name = {skill.name.lower(): skill for skill in skills_result.scalars().all()}

    user_ids = {user.id for user in users_by_username.values()}
    levels_result = await db.execute(
        select(SkillLevel).where(SkillLevel.user_id.in_(user_ids))
    )
    levels_by_user_skill = {
        (level.user_id, level.skill_id): level for level in levels_result.scalars().all()
    }

    imported_rows = 0
    skills_created = 0
    levels_created = 0
    levels_updated = 0

    for row in parsed.rows:
        user = users_by_username.get(row.username)
        if not user:
            errors.append(SkillsImportRowError(
                line=row.line, message=f"unknown username '{row.username}'"))
            continue
        if not user.is_active:
            errors.append(SkillsImportRowError(
                line=row.line, message=f"user '{row.username}' is deactivated"))
            continue

        skill = skills_by_name.get(row.skill_name.lower())
        if not skill:
            if not row.category:
                errors.append(SkillsImportRowError(
                    line=row.line,
                    message=(
                        f"skill '{row.skill_name}' is not in the catalogue; "
                        "provide a 'category' to create it"
                    ),
                ))
                continue
            skill = Skill(name=row.skill_name, category=row.category)
            db.add(skill)
            await db.flush()  # assign skill.id for the SkillLevel FK
            skills_by_name[skill.name.lower()] = skill
            skills_created += 1

        existing = levels_by_user_skill.get((user.id, skill.id))
        if existing:
            existing.level = row.level
            existing.aspiration_level = row.aspiration_level
            levels_updated += 1
        else:
            level = SkillLevel(
                user_id=user.id,
                skill_id=skill.id,
                level=row.level,
                aspiration_level=row.aspiration_level,
            )
            db.add(level)
            levels_by_user_skill[(user.id, skill.id)] = level
            levels_created += 1
        imported_rows += 1

    await db.commit()
    if imported_rows:
        await write_audit_log(
            db, current_user.id, "import_skill_levels", "skill_level", None,
            f"CSV import: {levels_created} levels created, {levels_updated} updated, "
            f"{skills_created} skills added, {len(errors)} rows skipped",
        )
        await db.commit()

    return SkillsImportResult(
        total_rows=len(parsed.rows) + len(parsed.errors),
        imported_rows=imported_rows,
        skills_created=skills_created,
        levels_created=levels_created,
        levels_updated=levels_updated,
        errors=errors,
    )
