"""Skill catalogue, skills matrix, team skills summary, and bulk import
(Requirements 2, 3, and 13)."""

from __future__ import annotations

import csv
import io

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.constants import (
    LEVEL_ORDER,
    LEVELS,
    SKILLS_IMPORT_OPTIONAL_COLUMNS,
    SKILLS_IMPORT_REQUIRED_COLUMNS,
)
from app.dtos import (
    ImportRowError,
    MatrixEntryDTO,
    RemovalResult,
    SkillDTO,
    SkillsImportResult,
    SkillSummaryDTO,
)
from app.exceptions import ConflictError, NotFoundError, StorageError, ValidationError
from app.models import Skill, SkillsMatrix, TeamMember, WorkItem, WorkItemSkill

# Canonical level lookup for case-insensitive matching of CSV values.
_LEVELS_BY_CASEFOLD: dict[str, str] = {level.casefold(): level for level in LEVELS}


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

    # -- Work item skills ----------------------------------------------------

    def list_ticket_skills(self, issue_key: str) -> list[SkillDTO]:
        """Skills linked to a Jira work item, ordered by name."""
        links = self._session.execute(
            select(WorkItemSkill)
            .options(joinedload(WorkItemSkill.skill))
            .where(WorkItemSkill.issue_key == issue_key.strip().upper())
        ).scalars()
        return sorted(
            (_skill_dto(link.skill) for link in links),
            key=lambda skill: skill.name.lower(),
        )

    def assign_ticket_skill(self, issue_key: str, skill_id: int) -> SkillDTO:
        """Link a catalogue skill to a cached work item. Idempotent: linking
        an already-linked skill is a no-op."""
        key = issue_key.strip().upper()
        if not self._work_item_exists(key):
            raise NotFoundError("That work item is not in the cache.")
        skill = self._session.get(Skill, skill_id)
        if skill is None:
            raise NotFoundError("That skill does not exist in the catalogue.")
        existing = self._session.execute(
            select(WorkItemSkill).where(
                WorkItemSkill.issue_key == key, WorkItemSkill.skill_id == skill_id
            )
        ).scalar_one_or_none()
        if existing is None:
            self._session.add(WorkItemSkill(issue_key=key, skill_id=skill_id))
            self._commit()
        return _skill_dto(skill)

    def remove_ticket_skill(self, issue_key: str, skill_id: int) -> SkillDTO:
        key = issue_key.strip().upper()
        link = self._session.execute(
            select(WorkItemSkill)
            .options(joinedload(WorkItemSkill.skill))
            .where(WorkItemSkill.issue_key == key, WorkItemSkill.skill_id == skill_id)
        ).scalar_one_or_none()
        if link is None:
            raise NotFoundError("That skill is not linked to this work item.")
        skill = _skill_dto(link.skill)
        self._session.delete(link)
        self._commit()
        return skill

    def _work_item_exists(self, issue_key: str) -> bool:
        return (
            self._session.execute(
                select(WorkItem.id).where(WorkItem.issue_key == issue_key)
            ).scalar_one_or_none()
            is not None
        )

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

    # -- Bulk import (Requirement 13) ----------------------------------------

    def import_matrix_csv(
        self, csv_text: str, create_missing_skills: bool = False
    ) -> SkillsImportResult:
        """Import skills matrix entries from CSV text, atomically.

        Every row is validated first; if any row fails, nothing is imported
        and the result carries one ``ImportRowError`` per failing row
        (Requirement 13.3). Valid rows create or update matrix entries
        exactly as ``assign_skill`` would, in a single commit. With
        ``create_missing_skills`` set, skills not in the catalogue are added
        as part of the same import (Requirement 13.4).
        """
        rows = self._parse_import_csv(csv_text)

        members_by_username = {
            member.username.casefold(): member
            for member in self._session.execute(select(TeamMember)).scalars()
        }
        skills_by_name = {
            skill.name.casefold(): skill
            for skill in self._session.execute(select(Skill)).scalars()
        }

        errors: list[ImportRowError] = []
        assignments: list[tuple[TeamMember, str, str, str | None]] = []
        pending_skills: dict[str, str] = {}  # casefolded name -> catalogue name
        seen_pairs: dict[tuple[str, str], int] = {}  # (username, skill) -> row number

        for row_number, cells in rows:
            username = cells.get("username", "")
            skill_name = cells.get("skill", "")
            row_errors = []

            member = members_by_username.get(username.casefold())
            if not username:
                row_errors.append(("username", "the username is missing."))
            elif member is None:
                row_errors.append(
                    ("username", "no team member has this username.")
                )

            skill_key = skill_name.casefold()
            if not skill_name:
                row_errors.append(("skill", "the skill name is missing."))
            elif skill_key not in skills_by_name and skill_key not in pending_skills:
                if create_missing_skills:
                    pending_skills[skill_key] = skill_name
                else:
                    row_errors.append(
                        (
                            "skill",
                            "this skill is not in the catalogue; add it first "
                            "or tick 'create missing skills'.",
                        )
                    )

            current = self._match_level(cells.get("current_level", ""))
            if current is None:
                row_errors.append(
                    (
                        "current_level",
                        f"the current proficiency level must be one of: {', '.join(LEVELS)}.",
                    )
                )

            aspiration_raw = cells.get("aspiration_level", "")
            aspiration = self._match_level(aspiration_raw) if aspiration_raw else None
            if aspiration_raw and aspiration is None:
                row_errors.append(
                    (
                        "aspiration_level",
                        f"the aspiration level must be one of: {', '.join(LEVELS)} (or empty).",
                    )
                )

            pair = (username.casefold(), skill_key)
            if not row_errors:
                if pair in seen_pairs:
                    row_errors.append(
                        (
                            "username",
                            "this team member and skill combination already "
                            f"appears at row {seen_pairs[pair]}.",
                        )
                    )
                else:
                    seen_pairs[pair] = row_number

            if row_errors:
                errors.extend(
                    ImportRowError(row_number=row_number, field=field, message=message)
                    for field, message in row_errors
                )
            else:
                assignments.append((member, skill_key, current, aspiration))

        if errors:
            return SkillsImportResult(errors=tuple(sorted(errors, key=lambda e: e.row_number)))

        for skill_key, name in pending_skills.items():
            skill = Skill(name=name)
            self._session.add(skill)
            skills_by_name[skill_key] = skill
        if pending_skills:
            self._session.flush()

        for member, skill_key, current, aspiration in assignments:
            skill = skills_by_name[skill_key]
            entry = self._session.execute(
                select(SkillsMatrix).where(
                    SkillsMatrix.member_id == member.id,
                    SkillsMatrix.skill_id == skill.id,
                )
            ).scalar_one_or_none()
            if entry is None:
                entry = SkillsMatrix(member_id=member.id, skill_id=skill.id)
                self._session.add(entry)
            entry.current_level = current
            entry.aspiration_level = aspiration
        self._commit()

        return SkillsImportResult(
            imported_count=len(assignments),
            member_count=len({member.id for member, *_ in assignments}),
            created_skills=tuple(pending_skills.values()),
        )

    def _parse_import_csv(self, csv_text: str) -> list[tuple[int, dict[str, str]]]:
        """Parse the data rows of an import CSV.

        Returns ``(row_number, {column: stripped value})`` pairs, with fully
        blank rows skipped. Raises ``ValidationError`` for file-level
        problems (Requirement 13.8): empty file, malformed CSV, missing
        required columns, or duplicate columns.
        """
        try:
            raw_rows = list(csv.reader(io.StringIO(csv_text)))
        except csv.Error as exc:
            raise ValidationError("The file is not a readable CSV file.") from exc
        if not raw_rows:
            raise ValidationError("The file is empty.")

        known_columns = SKILLS_IMPORT_REQUIRED_COLUMNS + SKILLS_IMPORT_OPTIONAL_COLUMNS
        header: dict[str, int] = {}
        for index, cell in enumerate(raw_rows[0]):
            name = cell.strip().casefold()
            if name in known_columns:
                if name in header:
                    raise ValidationError(
                        f"The header names the '{name}' column more than once."
                    )
                header[name] = index
        missing = [column for column in SKILLS_IMPORT_REQUIRED_COLUMNS if column not in header]
        if missing:
            raise ValidationError(
                "The header row must name the columns: "
                f"{', '.join(SKILLS_IMPORT_REQUIRED_COLUMNS)} "
                f"(missing: {', '.join(missing)})."
            )

        rows: list[tuple[int, dict[str, str]]] = []
        for row_number, raw in enumerate(raw_rows[1:], start=2):
            if not any(cell.strip() for cell in raw):
                continue
            cells = {
                column: (raw[index].strip() if index < len(raw) else "")
                for column, index in header.items()
            }
            rows.append((row_number, cells))
        return rows

    @staticmethod
    def _match_level(value: str) -> str | None:
        """Canonical proficiency level for a CSV value, or None."""
        return _LEVELS_BY_CASEFOLD.get(value.strip().casefold())

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
