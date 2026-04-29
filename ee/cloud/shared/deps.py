"""FastAPI dependencies for cloud routers."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException

from ee.cloud.auth import current_active_user
from ee.cloud.models.user import User
from ee.cloud.shared.errors import Forbidden
from pocketpaw.ee.guards.audit import log_denial
from pocketpaw.ee.guards.deps import check_workspace_action
from pocketpaw.ee.guards.rbac import Forbidden as GuardForbidden


async def current_user(user: User = Depends(current_active_user)) -> User:
    """Get the authenticated user from JWT token."""
    return user


async def current_user_id(user: User = Depends(current_active_user)) -> str:
    """Extract user ID from JWT token."""
    return str(user.id)


async def current_workspace_id(user: User = Depends(current_active_user)) -> str:
    """Extract active workspace ID from the authenticated user."""
    if not user.active_workspace:
        raise HTTPException(400, "No active workspace. Create or join a workspace first.")
    return user.active_workspace


async def optional_workspace_id(user: User = Depends(current_active_user)) -> str | None:
    """Extract workspace ID if set, or None."""
    return user.active_workspace


# ---------------------------------------------------------------------------
# Action-based guards (canonical from 2026-04-14)
# ---------------------------------------------------------------------------


async def _workspace_id_from_path(workspace_id: str) -> str:
    """Pull `workspace_id` from the path. FastAPI binds by parameter name."""
    return workspace_id


_WorkspaceIdDep = Callable[..., Coroutine[Any, Any, str]]


def require_action(
    action: str,
    workspace_dep: _WorkspaceIdDep = _workspace_id_from_path,
) -> Callable[..., Coroutine[Any, Any, User]]:
    """FastAPI dependency enforcing an ACTIONS entry against the caller's
    workspace role.

    Default `workspace_dep` reads `workspace_id` from the path. Pass
    `current_workspace_id` to read from the user's active workspace instead.

    On deny, raises the cloud-native `Forbidden` (CloudError) so the global
    exception handler emits the standard error envelope. Every denial is
    audited via `log_denial` already inside `check_workspace_action`, but we
    also surface the guard's `code` through the cloud envelope.
    """

    async def _guard(
        user: User = Depends(current_active_user),
        workspace_id: str = Depends(workspace_dep),
    ) -> User:
        try:
            check_workspace_action(user, workspace_id, action)
        except GuardForbidden as exc:
            # check_workspace_action already logged; re-raise as cloud
            # Forbidden so the API error envelope matches the rest of the
            # cloud module.
            raise Forbidden(exc.code, exc.detail or "Access denied") from exc
        return user

    _guard.__name__ = f"require_action_{action.replace('.', '_')}"
    return _guard


def require_action_any_workspace(action: str) -> Callable[..., Coroutine[Any, Any, User]]:
    """Variant of `require_action` that resolves workspace from the user's
    `active_workspace`. Use when the route has no `{workspace_id}` path param.
    """
    return require_action(action, workspace_dep=current_workspace_id)


async def require_membership(
    user: User = Depends(current_active_user),
    workspace_id: str = Depends(_workspace_id_from_path),
) -> User:
    """Light guard — just asserts the user is a member of the path workspace.
    Used on read routes where any member can view (no role check)."""
    for m in user.workspaces:
        if m.workspace == workspace_id:
            return user
    log_denial(
        actor=str(user.id),
        action="workspace.view",
        code="workspace.not_member",
        workspace_id=workspace_id,
    )
    raise Forbidden("workspace.not_member", "Not a member of this workspace")


# ---------------------------------------------------------------------------
# Group-scoped action guard
# ---------------------------------------------------------------------------


def require_group_action(action: str) -> Callable[..., Coroutine[Any, Any, User]]:
    """FastAPI dependency enforcing a group-scoped action.

    Loads the Group by `{group_id}` path param, resolves the caller's
    ``GroupRole`` via ``group_service.resolve_group_role``, and checks the
    ACTIONS rule for ``action``. Raises cloud ``Forbidden`` on deny.
    """
    from pocketpaw.ee.guards.actions import GroupRole, get_rule

    rule = get_rule(action)

    async def _guard(
        group_id: str,
        user: User = Depends(current_active_user),
    ) -> User:
        # Lazy imports to avoid circular dependency (chat → shared.deps → chat).
        from beanie import PydanticObjectId

        from ee.cloud.chat.group_service import resolve_group_role
        from ee.cloud.models.group import Group
        from ee.cloud.shared.errors import NotFound

        group = await Group.get(PydanticObjectId(group_id))
        if not group:
            raise NotFound("group", group_id)

        try:
            role = resolve_group_role(group, str(user.id))
            if isinstance(rule.minimum, GroupRole) and role.level < rule.minimum.level:
                log_denial(
                    actor=str(user.id),
                    action=action,
                    code=rule.deny_code,
                    resource_id=group_id,
                )
                raise GuardForbidden(
                    code=rule.deny_code,
                    detail=f"Requires {rule.minimum.value}, got {role.value}",
                )
        except GuardForbidden as exc:
            raise Forbidden(exc.code, exc.detail or "Access denied") from exc
        return user

    _guard.__name__ = f"require_group_action_{action.replace('.', '_')}"
    return _guard


# ---------------------------------------------------------------------------
# Agent-scoped action guard (owner OR workspace admin)
# ---------------------------------------------------------------------------


async def require_agent_owner_or_admin(
    agent_id: str,
    user: User = Depends(current_active_user),
) -> User:
    """Allow the action if the caller is the agent's owner OR a workspace
    admin (or owner) of the agent's workspace.

    Raises cloud ``Forbidden`` with ``agent.not_owner`` if neither.
    """
    from beanie import PydanticObjectId

    from ee.cloud.models.agent import Agent as AgentModel
    from ee.cloud.shared.errors import NotFound
    from pocketpaw.ee.guards.deps import resolve_workspace_role
    from pocketpaw.ee.guards.rbac import WorkspaceRole

    try:
        agent_oid = PydanticObjectId(agent_id)
    except Exception as exc:  # noqa: BLE001
        raise NotFound("agent", agent_id) from exc

    agent = await AgentModel.get(agent_oid)
    if not agent:
        raise NotFound("agent", agent_id)

    user_id = str(user.id)
    if agent.owner == user_id:
        return user

    # Not the owner — check workspace admin+
    try:
        role = resolve_workspace_role(user, agent.workspace)
        if role.level >= WorkspaceRole.ADMIN.level:
            return user
    except GuardForbidden:
        pass  # fall through to deny

    log_denial(
        actor=user_id,
        action="agent.edit",
        code="agent.not_owner",
        resource_id=agent_id,
        workspace_id=agent.workspace,
    )
    raise Forbidden("agent.not_owner", "Only the agent owner or a workspace admin may do this")


# ---------------------------------------------------------------------------
# Pocket-scoped action guards
# ---------------------------------------------------------------------------


async def require_pocket_edit(
    pocket_id: str,
    user: User = Depends(current_active_user),
) -> User:
    """Allow if the caller is pocket.owner, in pocket.shared_with, or the
    pocket is workspace-visible. Mirrors ``_check_edit_access`` from
    ``pockets/service.py`` but enforced before the handler runs.
    """
    from beanie import PydanticObjectId

    from ee.cloud.models.pocket import Pocket
    from ee.cloud.shared.errors import NotFound

    try:
        pocket_oid = PydanticObjectId(pocket_id)
    except Exception as exc:  # noqa: BLE001
        raise NotFound("pocket", pocket_id) from exc

    pocket = await Pocket.get(pocket_oid)
    if not pocket:
        raise NotFound("pocket", pocket_id)

    user_id = str(user.id)
    if pocket.owner == user_id:
        return user
    if user_id in (pocket.shared_with or []):
        return user
    if pocket.visibility == "workspace":
        return user

    log_denial(
        actor=user_id,
        action="pocket.edit",
        code="pocket.access_denied",
        resource_id=pocket_id,
    )
    raise Forbidden("pocket.access_denied", "You do not have edit access to this pocket")


async def require_pocket_owner(
    pocket_id: str,
    user: User = Depends(current_active_user),
) -> User:
    """Allow only the pocket owner. Used for share-link, delete, and
    collaborator mutations."""
    from beanie import PydanticObjectId

    from ee.cloud.models.pocket import Pocket
    from ee.cloud.shared.errors import NotFound

    try:
        pocket_oid = PydanticObjectId(pocket_id)
    except Exception as exc:  # noqa: BLE001
        raise NotFound("pocket", pocket_id) from exc

    pocket = await Pocket.get(pocket_oid)
    if not pocket:
        raise NotFound("pocket", pocket_id)

    if pocket.owner == str(user.id):
        return user

    log_denial(
        actor=str(user.id),
        action="pocket.share",
        code="pocket.not_owner",
        resource_id=pocket_id,
    )
    raise Forbidden("pocket.not_owner", "Only the pocket owner can perform this action")
