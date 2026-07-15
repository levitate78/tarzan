"""Team member profile CRUD and avatar handling (Requirement 1)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.constants import ALLOWED_AVATAR_MIME_TYPES, MAX_AVATAR_BYTES
from app.dtos import ProfileDTO
from app.exceptions import ConflictError, NotFoundError, StorageError, ValidationError
from app.models import TeamMember

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CreateProfileInput:
    name: str
    username: str
    jira_account_id: str | None = None
    gitlab_username: str | None = None


@dataclass(frozen=True)
class UpdateProfileInput:
    name: str
    username: str
    jira_account_id: str | None = None
    gitlab_username: str | None = None


def _to_dto(member: TeamMember) -> ProfileDTO:
    return ProfileDTO(
        username=member.username,
        name=member.name,
        avatar_path=member.avatar_path,
        jira_account_id=member.jira_account_id,
        gitlab_username=member.gitlab_username,
    )


class ProfileService:
    def __init__(self, session: Session, avatars_dir: Path):
        self._session = session
        self._avatars_dir = avatars_dir

    # -- Queries ---------------------------------------------------------

    def list_profiles(self) -> list[ProfileDTO]:
        members = self._session.execute(
            select(TeamMember).order_by(func.lower(TeamMember.name))
        ).scalars()
        return [_to_dto(member) for member in members]

    def get_profile(self, username: str) -> ProfileDTO | None:
        member = self._get_member(username)
        return _to_dto(member) if member is not None else None

    # -- Mutations ---------------------------------------------------------

    def create_profile(self, data: CreateProfileInput) -> ProfileDTO:
        name = self._validate_required(data.name, "name")
        username = self._validate_required(data.username, "username")
        self._ensure_username_free(username)
        member = TeamMember(
            name=name,
            username=username,
            jira_account_id=(data.jira_account_id or "").strip() or None,
            gitlab_username=(data.gitlab_username or "").strip() or None,
        )
        self._session.add(member)
        self._commit()
        return _to_dto(member)

    def update_profile(self, username: str, data: UpdateProfileInput) -> ProfileDTO:
        member = self._get_member(username)
        if member is None:
            raise NotFoundError(f"No team member with username {username!r}.")
        new_name = self._validate_required(data.name, "name")
        new_username = self._validate_required(data.username, "username")
        if new_username.lower() != member.username.lower():
            self._ensure_username_free(new_username)
        member.name = new_name
        member.username = new_username
        member.jira_account_id = (data.jira_account_id or "").strip() or None
        member.gitlab_username = (data.gitlab_username or "").strip() or None
        self._commit()
        return _to_dto(member)

    def save_avatar(self, username: str, file_bytes: bytes, mime_type: str) -> str:
        """Validate and store an avatar; returns the stored file path
        (Requirement 1.7)."""
        member = self._get_member(username)
        if member is None:
            raise NotFoundError(f"No team member with username {username!r}.")
        extension = ALLOWED_AVATAR_MIME_TYPES.get((mime_type or "").lower())
        if extension is None:
            raise ValidationError(
                "Avatar must be a JPEG, PNG, GIF, or WebP image.", field="avatar"
            )
        if len(file_bytes) > MAX_AVATAR_BYTES:
            raise ValidationError(
                "Avatar file is too large: the maximum size is 5 MB.", field="avatar"
            )
        self._avatars_dir.mkdir(parents=True, exist_ok=True)
        # Filename derives from the member id (not user input) to prevent
        # path traversal; verify the resolved path stays inside the store.
        target = (self._avatars_dir / f"member-{member.id}.{extension}").resolve()
        if not target.is_relative_to(self._avatars_dir.resolve()):
            raise ValidationError("Invalid avatar path.", field="avatar")

        # Remove any previous avatar with a different extension.
        old_path = Path(member.avatar_path) if member.avatar_path else None
        target.write_bytes(file_bytes)
        member.avatar_path = str(target)
        self._commit()
        if old_path and old_path.resolve() != target and old_path.exists():
            try:
                old_path.unlink()
            except OSError:
                logger.warning("Could not remove previous avatar file")
        return str(target)

    def resolve_avatar_file(self, username: str) -> Path | None:
        """Return the avatar path for serving, validated to be inside the
        avatar directory (path traversal defence)."""
        member = self._get_member(username)
        if member is None or not member.avatar_path:
            return None
        path = Path(member.avatar_path).resolve()
        if not path.is_relative_to(self._avatars_dir.resolve()) or not path.exists():
            return None
        return path

    # -- Internals ---------------------------------------------------------

    def _get_member(self, username: str) -> TeamMember | None:
        """Case-insensitive lookup. Comparison happens in Python with
        casefold() because SQLite's lower() only folds ASCII."""
        if not username:
            return None
        wanted = username.strip().casefold()
        for member in self._session.execute(select(TeamMember)).scalars():
            if member.username.casefold() == wanted:
                return member
        return None

    @staticmethod
    def _validate_required(value: str | None, field: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValidationError(
                f"The {field} field is required and cannot be empty.", field=field
            )
        return cleaned

    def _ensure_username_free(self, username: str) -> None:
        existing = self._get_member(username)
        if existing is not None:
            raise ConflictError(
                "That username is already in use by another team member."
            )

    def _commit(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError(
                "That username is already in use by another team member."
            ) from exc
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise StorageError("Could not save the profile.") from exc
