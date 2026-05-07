"""Team role / permission matrix.

Three roles, each with a fixed set of capabilities. Adding a new
capability is a one-line edit to ``ROLE_PERMISSIONS``; adding a new
role means a new key in the same dict — call sites already go
through :func:`has_permission`.

Roles (canonical order, most → least powerful):

* **owner** — full control. Billing, deleting the team, transferring
  ownership. There is exactly one owner per team.
* **admin** — runs the workspace day to day. Can invite / remove
  members, edit any lead, change settings. Can NOT touch billing or
  delete the team. Multiple admins per team are fine.
* **member** — uses the workspace. Runs searches, edits own leads,
  views the shared team CRM. Can't manage other members.

The legacy ``viewer`` role from the early team prototype is treated
as a synonym for ``member`` for backward compatibility — old rows
stored ``viewer`` before this module existed and we don't need a
migration to keep them functioning.

Why a permission table instead of role checks at each call site:
the same operation (e.g. "edit team settings") today is checked at
3 routes and will be at 5 once the UI matures. A central matrix
means a future "delegate billing to admins" decision is a one-line
flip; a literal ``role == "owner"`` audit becomes a grep.
"""

from __future__ import annotations

from typing import Final

# Canonical role names. Anything else gets normalised to ``member``
# before lookup so legacy / unknown values fail closed (least
# powerful), never open.
ROLE_OWNER: Final[str] = "owner"
ROLE_ADMIN: Final[str] = "admin"
ROLE_MEMBER: Final[str] = "member"

# Capability slugs. Each call site asks for one of these via
# ``has_permission(role, "edit_team_settings")``.
PERM_MANAGE_BILLING: Final[str] = "manage_billing"
PERM_DELETE_TEAM: Final[str] = "delete_team"
PERM_TRANSFER_OWNERSHIP: Final[str] = "transfer_ownership"
PERM_MANAGE_MEMBERS: Final[str] = "manage_members"
PERM_EDIT_TEAM_SETTINGS: Final[str] = "edit_team_settings"
PERM_EDIT_TEAM_LEADS: Final[str] = "edit_team_leads"
PERM_RUN_SEARCH: Final[str] = "run_search"
PERM_VIEW_TEAM: Final[str] = "view_team"


_ALL_PERMS: frozenset[str] = frozenset(
    {
        PERM_MANAGE_BILLING,
        PERM_DELETE_TEAM,
        PERM_TRANSFER_OWNERSHIP,
        PERM_MANAGE_MEMBERS,
        PERM_EDIT_TEAM_SETTINGS,
        PERM_EDIT_TEAM_LEADS,
        PERM_RUN_SEARCH,
        PERM_VIEW_TEAM,
    }
)


# Source of truth for the role → capabilities mapping. Owner gets
# everything by definition (computed below to avoid drift). Admin
# gets everything except billing + the destructive team-level ops.
# Member gets the day-to-day usage set.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_OWNER: _ALL_PERMS,
    ROLE_ADMIN: frozenset(
        {
            PERM_MANAGE_MEMBERS,
            PERM_EDIT_TEAM_SETTINGS,
            PERM_EDIT_TEAM_LEADS,
            PERM_RUN_SEARCH,
            PERM_VIEW_TEAM,
        }
    ),
    ROLE_MEMBER: frozenset(
        {
            PERM_RUN_SEARCH,
            PERM_VIEW_TEAM,
        }
    ),
}


# Roles the owner is allowed to assign. Excludes ``owner`` itself —
# transferring ownership is a separate flow that swaps the active
# owner row, not a free assignment.
ASSIGNABLE_ROLES: tuple[str, ...] = (ROLE_ADMIN, ROLE_MEMBER)


def normalize_role(role: str | None) -> str:
    """Canonicalise a stored role value.

    Unknown / legacy values (``"viewer"`` from the prototype) collapse
    to ``member`` so a malformed row doesn't accidentally grant power.
    """
    if not role:
        return ROLE_MEMBER
    lowered = role.strip().lower()
    if lowered in ROLE_PERMISSIONS:
        return lowered
    return ROLE_MEMBER


def has_permission(role: str | None, permission: str) -> bool:
    """Return True iff ``role`` is allowed to perform ``permission``."""
    return permission in ROLE_PERMISSIONS.get(normalize_role(role), frozenset())


def can_manage_members(role: str | None) -> bool:
    """Convenience: can this role invite / remove / re-role members?"""
    return has_permission(role, PERM_MANAGE_MEMBERS)


def can_edit_team_settings(role: str | None) -> bool:
    """Convenience: can this role rename the team / edit description?"""
    return has_permission(role, PERM_EDIT_TEAM_SETTINGS)
