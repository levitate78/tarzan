from __future__ import annotations

from enum import Enum
from typing import Set


class Role(str, Enum):
    admin = "admin"
    lead = "lead"
    member = "member"
    viewer = "viewer"


# Numeric weights — higher = more access
_WEIGHT: dict[Role, int] = {
    Role.admin: 40,
    Role.lead: 30,
    Role.member: 20,
    Role.viewer: 10,
}


def has_role(user_role: str, required: Role) -> bool:
    """Return True if *user_role* meets or exceeds *required*."""
    try:
        return _WEIGHT[Role(user_role)] >= _WEIGHT[required]
    except KeyError:
        return False


# ── Named permission sets (for readability) ────────────────────────────────────

def can_admin(role: str) -> bool:
    return has_role(role, Role.admin)


def can_manage_team(role: str) -> bool:
    return has_role(role, Role.lead)


def can_reassign(role: str) -> bool:
    return has_role(role, Role.lead)


def can_view(role: str) -> bool:
    return has_role(role, Role.viewer)