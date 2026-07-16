"""CSV parsing/validation for the bulk skill-level import.

Kept free of database and framework imports so it can be unit-tested
without a running application (see ``tests/test_skills_csv.py``). The
router in ``app.skills_import`` consumes the parsed rows.

Expected CSV format (header row required, column order free,
header names case-insensitive):

    username,skill,level,aspiration_level,category

- ``username``          Tarzan username of the team member (required)
- ``skill``             skill name, matched case-insensitively against the
                        catalogue (required)
- ``level``             integer 0-5 or a level name (required)
- ``aspiration_level``  integer 0-5 or a level name, may be blank (optional
                        column)
- ``category``          skill category; only used to create a skill that is
                        not in the catalogue yet (optional column)
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Optional

from app.schemas import SkillCategory

MAX_ROWS = 5000
LEVEL_MIN = 0
LEVEL_MAX = 5

# Named proficiency levels (spec: .kiro/specs/team-dashboard) mapped onto the
# 0-5 scale the application stores (see SkillLevelSet in openapi.yaml).
LEVEL_NAMES = {
    "none": 0,
    "beginner": 1,
    "elementary": 2,
    "intermediate": 3,
    "advanced": 4,
    "expert": 5,
}

REQUIRED_COLUMNS = ("username", "skill", "level")
OPTIONAL_COLUMNS = ("aspiration_level", "category")

VALID_CATEGORIES = frozenset(c.value for c in SkillCategory)


class SkillsCsvError(ValueError):
    """Structural problem with the CSV (missing/duplicate header columns)."""


@dataclass
class SkillsCsvRow:
    line: int  # 1-based line number in the file (header is line 1)
    username: str
    skill_name: str
    level: int
    aspiration_level: Optional[int]
    category: Optional[str]


@dataclass
class SkillsCsvParseResult:
    rows: list[SkillsCsvRow] = field(default_factory=list)
    errors: list[tuple[int, str]] = field(default_factory=list)  # (line, message)

    @property
    def total_rows(self) -> int:
        return len(self.rows) + len(self.errors)


# Per the spec's input-validation requirement, error messages describe the
# problem and the valid values but never echo the invalid value back.
def _parse_level(raw: str, column: str, *, required: bool) -> Optional[int]:
    value = raw.strip()
    if not value:
        if required:
            raise ValueError(f"'{column}' is required")
        return None
    named = LEVEL_NAMES.get(value.lower())
    if named is not None:
        return named
    try:
        level = int(value)
    except ValueError:
        raise ValueError(
            f"'{column}' must be an integer between {LEVEL_MIN} and {LEVEL_MAX} "
            f"or one of: {', '.join(LEVEL_NAMES)}"
        ) from None
    if not LEVEL_MIN <= level <= LEVEL_MAX:
        raise ValueError(f"'{column}' must be between {LEVEL_MIN} and {LEVEL_MAX}")
    return level


def parse_skills_csv(content: str) -> SkillsCsvParseResult:
    """Parse and validate the CSV. Structural problems raise SkillsCsvError;
    per-row problems are collected in the result's ``errors`` list."""
    reader = csv.reader(io.StringIO(content))
    try:
        raw_header = next(reader)
    except StopIteration:
        raise SkillsCsvError("CSV is empty") from None

    header = [column.strip().lower() for column in raw_header]
    if len(set(header)) != len(header):
        raise SkillsCsvError("CSV header contains duplicate columns")
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise SkillsCsvError(
            f"CSV header is missing required column(s): {', '.join(missing)}. "
            f"Required: {', '.join(REQUIRED_COLUMNS)}; optional: {', '.join(OPTIONAL_COLUMNS)}"
        )
    index = {column: header.index(column) for column in header}

    def cell(record: list[str], column: str) -> str:
        pos = index.get(column)
        if pos is None or pos >= len(record):
            return ""
        return record[pos].strip()

    result = SkillsCsvParseResult()
    seen: set[tuple[str, str]] = set()

    for line, record in enumerate(reader, start=2):
        if not any(value.strip() for value in record):
            continue  # blank line
        if len(result.rows) + len(result.errors) >= MAX_ROWS:
            result.errors.append((line, f"Too many rows; a single import is limited to {MAX_ROWS}"))
            break

        username = cell(record, "username")
        skill_name = cell(record, "skill")
        category = cell(record, "category").lower() or None

        try:
            if not username:
                raise ValueError("'username' is required")
            if not skill_name:
                raise ValueError("'skill' is required")
            if category is not None and category not in VALID_CATEGORIES:
                raise ValueError(
                    f"unknown category (valid: {', '.join(sorted(VALID_CATEGORIES))})"
                )
            level = _parse_level(cell(record, "level"), "level", required=True)
            aspiration = _parse_level(cell(record, "aspiration_level"), "aspiration_level", required=False)

            key = (username, skill_name.lower())
            if key in seen:
                raise ValueError("duplicate of an earlier row for the same user and skill")
            seen.add(key)
        except ValueError as exc:
            result.errors.append((line, str(exc)))
            continue

        result.rows.append(
            SkillsCsvRow(
                line=line,
                username=username,
                skill_name=skill_name,
                level=level,  # type: ignore[arg-type]  # required=True never returns None
                aspiration_level=aspiration,
                category=category,
            )
        )

    return result
