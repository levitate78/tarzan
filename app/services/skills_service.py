"""Skill catalogue, skills matrix, and team skills summary
(Requirements 2 and 3)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.constants import LEVEL_ORDER, LEVELS
from app.dtos import MatrixEntryDTO, RemovalResult, SkillDTO, SkillSummaryDTO
from app.exceptions import ConflictError, NotFoundError, StorageError, ValidationError
from app.models import Skill, SkillsMatrix, TeamMember


def _skill_dto(skill: Skill) -> SkillDTO:
    return SkillDTO(id=skill.id, name=skill.name, deprecated=skill.deprecated)


class SkillsService:
    def __init__(self, session: Session):
        self._session = session

    # -- Catalogue ---------------------------------------------------------

    def list_catalogue(self, include_deprecated: bool = True) -> list[SkillDTO]:
        query = select(Skill).order_by(func.lower(Skill.name))
        if not include_deprecated:
            query = query.where(Skill.deprecated.is_(False))
        return [_skill_dto(skill) for skill in self._session.execute(query).scalars()]

    def add_skill(self, name: str) -> SkillDTO:
        cleaned = (name or "").strip()
        if not cleaned:
            raise ValidationError("The skill name is required and cannot be empty.", field="name")
        wanted = cleaned.casefold()
        for existing in self._session.execute(select(Skill)).scalars():
            if existing.name.casefold() == wanted:
                raise ConflictError("A skill with that name already exists in the catalogue.")
        skill = Skill(name=cleaned)
        self._session.add(skill)
        self._commit()
        return _skill_dto(skill)

    def reference_count(self, skill_id: int) -> int:
        return (
            self._session.execute(
                select(func.count(SkillsMatrix.id)).where(SkillsMatrix.skill_id == skill_id)
            ).scalar_one()
            or 0
        )

    def get_skill(self, skill_id: int) -> SkillDTO | None:
        skill = self._session.get(Skill, skill_id)
        return _skill_dto(skill) if skill is not None else None

    def remove_skill(self, skill_id: int) -> RemovalResult:
        """Delete an unreferenced skill; deprecate a referenced one so
        existing matrix entries are preserved (Requirement 2.4)."""
        skill = self._session.get(Skill, skill_id)
        if skill is None:
            raise NotFoundError("That skill does not exist in the catalogue.")
        references = self.reference_count(skill_id)
        if references == 0:
            self._session.delete(skill)
            self._commit()
            return RemovalResult(
                skill_id=skill_id,
                skill_name=skill.name,
                reference_count=0,
                removed=True,
                deprecated=False,
            )
        skill.deprecated = True
        self._commit()
        return RemovalResult(
            skill_id=skill_id,
            skill_name=skill.name,
            reference_count=references,
            removed=False,
            deprecated=True,
        )

    # -- Skills matrix -------------------------------------------------------

    def list_matrix(self, username: str) -> list[MatrixEntryDTO]:
        member = self._get_member(username)
        entries = self._session.execute(
            select(SkillsMatrix)
            .options(joinedload(SkillsMatrix.skill))
            .where(SkillsMatrix.member_id == member.id)
        ).scalars()
        return sorted(
            (
                MatrixEntryDTO(
                    skill_id=entry.skill_id,
                    skill_name=entry.skill.name,
                    skill_deprecated=entry.skill.deprecated,
                    current_level=entry.current_level,
                    aspiration_level=entry.aspiration_level,
                )
                for entry in entries
            ),
            key=lambda entry: entry.skill_name.lower(),
        )

    def assign_skill(
        self,
        username: str,
        skill_id: int,
        current: str,
        aspiration: str | None = None,
    ) -> None:
        member = self._get_member(username)
        skill = self._session.get(Skill, skill_id)
        if skill is None:
            raise NotFoundError("That skill does not exist in the catalogue.")
        current_level = self._validate_level(current, "current proficiency level")
        aspiration_level = (
            self._validate_level(aspiration, "aspiration level") if aspiration else None
        )
        entry = self._session.execute(
            select(SkillsMatrix).where(
                SkillsMatrix.member_id == member.id, SkillsMatrix.skill_id == skill_id
            )
        ).scalar_one_or_none()
        if entry is None:
            entry = SkillsMatrix(member_id=member.id, skill_id=skill_id)
            self._session.add(entry)
        entry.current_level = current_level
        entry.aspiration_level = aspiration_level
        self._commit()

    def remove_matrix_entry(self, username: str, skill_id: int) -> None:
        member = self._get_member(username)
        entry = self._session.execute(
            select(SkillsMatrix).where(
                SkillsMatrix.member_id == member.id, SkillsMatrix.skill_id == skill_id
            )
        ).scalar_one_or_none()
        if entry is None:
            raise NotFoundError("That skill is not in this team member's skills matrix.")
        self._session.delete(entry)
        self._commit()

    # -- Team summary (Requirement 3) ---------------------------------------

    def get_team_skills_summary(self) -> list[SkillSummaryDTO]:
        """Every catalogue skill with per-level counts (zeros included) and
        the count of members aspiring above their current level."""
        skills = self._session.execute(
            select(Skill).order_by(func.lower(Skill.name))
        ).scalars().all()
        entries = self._session.execute(select(SkillsMatrix)).scalars().all()

        by_skill: dict[int, list[SkillsMatrix]] = {}
        for entry in entries:
            by_skill.setdefault(entry.skill_id, []).append(entry)

        summaries = []
        for skill in skills:
            skill_entries = by_skill.get(skill.id, [])
            level_counts = {level: 0 for level in LEVELS}
            aspiration_count = 0
            for entry in skill_entries:
                if entry.current_level in level_counts:
                    level_counts[entry.current_level] += 1
                if (
                    entry.aspiration_level in LEVEL_ORDER
                    and entry.current_level in LEVEL_ORDER
                    and LEVEL_ORDER[entry.aspiration_level] > LEVEL_ORDER[entry.current_level]
                ):
                    aspiration_count += 1
            summaries.append(
                SkillSummaryDTO(
                    skill_id=skill.id,
                    skill_name=skill.name,
                    deprecated=skill.deprecated,
                    level_counts=level_counts,
                    aspiration_count=aspiration_count,
                )
            )
        return summaries

    # -- Internals ---------------------------------------------------------

    def _get_member(self, username: str) -> TeamMember:
        """Case-insensitive lookup, casefolded in Python (SQLite lower() is
        ASCII-only)."""
        wanted = (username or "").strip().casefold()
        for member in self._session.execute(select(TeamMember)).scalars():
            if member.username.casefold() == wanted:
                return member
        raise NotFoundError(f"No team member with username {username!r}.")

    @staticmethod
    def _validate_level(value: str | None, label: str) -> str:
        if value not in LEVELS:
            raise ValidationError(
                f"The {label} must be one of: {', '.join(LEVELS)}.", field=label
            )
        return value

    def _commit(self) -> None:
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise StorageError("Could not save the skills change.") from exc
