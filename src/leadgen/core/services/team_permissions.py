"""Team role / permission matrix.

Four roles, each with a fixed set of capabilities. Adding a new
capability is a one-line edit to ``ROLE_PERMISSIONS``; adding a new
role means a new key in the same dict — call sites already go
through :func:`has_permission`.

Roles (canonical order, most → least powerful):

* **owner** — full control. Billing, deleting the team, transferring
  ownership, cost ceilings. There is exactly one owner per team.
* **admin** — runs the workspace day to day. Can invite / remove
  members, edit settings and integrations, see the audit log. Can
  NOT touch billing or delete the team. Multiple admins are fine.
* **manager** — runs the sales department. Prospecting ("Добыча"),
  the full team lead base ("База"), funnels, analytics, exports,
  distributing leads to sales reps. Can't manage members or team
  settings.
* **sales** — works assigned leads only ("Работа" / "Входящие").
  No searching / prospecting, no exports, no analytics, no money
  fields, no view into teammates' pipelines.

Legacy roles from earlier prototypes are normalised on read:
``member`` (could run searches, saw the shared CRM) maps to
``manager``; ``viewer`` (read-only share) maps to ``sales``.
Unknown / malformed values collapse to ``sales`` so a bad row fails
closed (least powerful), never open.

Why a permission table instead of role checks at each call site:
the same operation (e.g. "edit team settings") today is checked at
3 routes and will be at 5 once the UI matures. A central matrix
means a future "delegate billing to admins" decision is a one-line
flip; a literal ``role == "owner"`` audit becomes a grep.
"""

from __future__ import annotations

from typing import Final

# Canonical role names.
ROLE_OWNER: Final[str] = "owner"
ROLE_ADMIN: Final[str] = "admin"
ROLE_MANAGER: Final[str] = "manager"
ROLE_SALES: Final[str] = "sales"

# Legacy stored values → canonical role. Kept tiny on purpose; rows
# written by the current code always store canonical names.
_LEGACY_ROLE_MAP: Final[dict[str, str]] = {
    "member": ROLE_MANAGER,
    "viewer": ROLE_SALES,
}

# Capability slugs. Each call site asks for one of these via
# ``has_permission(role, PERM_...)``.
PERM_MANAGE_BILLING: Final[str] = "manage_billing"
PERM_DELETE_TEAM: Final[str] = "delete_team"
PERM_TRANSFER_OWNERSHIP: Final[str] = "transfer_ownership"
PERM_MANAGE_MEMBERS: Final[str] = "manage_members"
PERM_EDIT_TEAM_SETTINGS: Final[str] = "edit_team_settings"
PERM_VIEW_AUDIT_LOG: Final[str] = "view_audit_log"
PERM_RUN_SEARCH: Final[str] = "run_search"
PERM_VIEW_ALL_LEADS: Final[str] = "view_all_leads"
PERM_ASSIGN_LEADS: Final[str] = "assign_leads"
PERM_MANAGE_FUNNELS: Final[str] = "manage_funnels"
PERM_MANAGE_STATUSES: Final[str] = "manage_statuses"
PERM_VIEW_ANALYTICS: Final[str] = "view_analytics"
PERM_EXPORT_LEADS: Final[str] = "export_leads"
PERM_VIEW_MONEY: Final[str] = "view_money"
PERM_WORK_LEADS: Final[str] = "work_leads"
PERM_VIEW_TEAM: Final[str] = "view_team"

_ALL_PERMS: frozenset[str] = frozenset(
    {
        PERM_MANAGE_BILLING,
        PERM_DELETE_TEAM,
        PERM_TRANSFER_OWNERSHIP,
        PERM_MANAGE_MEMBERS,
        PERM_EDIT_TEAM_SETTINGS,
        PERM_VIEW_AUDIT_LOG,
        PERM_RUN_SEARCH,
        PERM_VIEW_ALL_LEADS,
        PERM_ASSIGN_LEADS,
        PERM_MANAGE_FUNNELS,
        PERM_MANAGE_STATUSES,
        PERM_VIEW_ANALYTICS,
        PERM_EXPORT_LEADS,
        PERM_VIEW_MONEY,
        PERM_WORK_LEADS,
        PERM_VIEW_TEAM,
    }
)

_MANAGER_PERMS: frozenset[str] = frozenset(
    {
        PERM_RUN_SEARCH,
        PERM_VIEW_ALL_LEADS,
        PERM_ASSIGN_LEADS,
        PERM_MANAGE_FUNNELS,
        PERM_MANAGE_STATUSES,
        PERM_VIEW_ANALYTICS,
        PERM_EXPORT_LEADS,
        PERM_VIEW_MONEY,
        PERM_WORK_LEADS,
        PERM_VIEW_TEAM,
    }
)

# Source of truth for the role → capabilities mapping. Owner gets
# everything by definition. Admin gets everything except billing +
# the destructive team-level ops. Manager gets the department set.
# Sales gets only their own work surface.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_OWNER: _ALL_PERMS,
    ROLE_ADMIN: _MANAGER_PERMS
    | frozenset(
        {
            PERM_MANAGE_MEMBERS,
            PERM_EDIT_TEAM_SETTINGS,
            PERM_VIEW_AUDIT_LOG,
        }
    ),
    ROLE_MANAGER: _MANAGER_PERMS,
    ROLE_SALES: frozenset(
        {
            PERM_WORK_LEADS,
            PERM_VIEW_TEAM,
        }
    ),
}


# Roles an ADMIN may hand out. Excludes ``admin`` (peers can't mint
# peers) and ``owner`` (transfer of ownership is a separate flow).
ADMIN_ASSIGNABLE_ROLES: tuple[str, ...] = (ROLE_MANAGER, ROLE_SALES)

# Roles the OWNER may hand out. Everything except ``owner`` itself.
OWNER_ASSIGNABLE_ROLES: tuple[str, ...] = (
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SALES,
)

# Backwards-compatible alias — old call sites treated this as "what
# a non-owner manager-of-members can assign".
ASSIGNABLE_ROLES: tuple[str, ...] = ADMIN_ASSIGNABLE_ROLES


def normalize_role(role: str | None) -> str:
    """Canonicalise a stored role value.

    Legacy values (``member`` / ``viewer`` from earlier prototypes)
    map to their modern equivalents; unknown values collapse to
    ``sales`` so a malformed row doesn't accidentally grant power.
    """
    if not role:
        return ROLE_SALES
    lowered = role.strip().lower()
    if lowered in ROLE_PERMISSIONS:
        return lowered
    return _LEGACY_ROLE_MAP.get(lowered, ROLE_SALES)


def has_permission(role: str | None, permission: str) -> bool:
    """Return True iff ``role`` is allowed to perform ``permission``."""
    return permission in ROLE_PERMISSIONS.get(normalize_role(role), frozenset())


def assignable_roles_for(caller_role: str | None) -> tuple[str, ...]:
    """Which roles may ``caller_role`` assign to others (invite or
    role-change)? Empty for roles without member management."""
    canonical = normalize_role(caller_role)
    if canonical == ROLE_OWNER:
        return OWNER_ASSIGNABLE_ROLES
    if canonical == ROLE_ADMIN:
        return ADMIN_ASSIGNABLE_ROLES
    return ()


def can_manage_members(role: str | None) -> bool:
    """Convenience: can this role invite / remove / re-role members?"""
    return has_permission(role, PERM_MANAGE_MEMBERS)


def can_edit_team_settings(role: str | None) -> bool:
    """Convenience: can this role rename the team / edit description?"""
    return has_permission(role, PERM_EDIT_TEAM_SETTINGS)


def can_run_search(role: str | None) -> bool:
    """Convenience: can this role launch prospecting searches?"""
    return has_permission(role, PERM_RUN_SEARCH)


def can_view_all_leads(role: str | None) -> bool:
    """Convenience: can this role browse the whole team base (and
    other members' pipelines)?"""
    return has_permission(role, PERM_VIEW_ALL_LEADS)


def can_view_money(role: str | None) -> bool:
    """Convenience: may money fields (deal value etc.) be shown?"""
    return has_permission(role, PERM_VIEW_MONEY)


def is_sales(role: str | None) -> bool:
    """Convenience: is this the assigned-leads-only role?"""
    return normalize_role(role) == ROLE_SALES
