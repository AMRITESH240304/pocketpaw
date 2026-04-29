"""Workspace domain — FastAPI router.

Authorization is declared at the route level via `require_action(...)`. Service
methods are auth-agnostic (they assume the caller has already been vetted).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from starlette.responses import Response

from ee.cloud.license import require_license
from ee.cloud.models.user import User
from ee.cloud.shared.deps import (
    current_user,
    require_action,
    require_membership,
)
from ee.cloud.workspace.schemas import (
    CreateInviteRequest,
    CreateWorkspaceRequest,
    UpdateMemberRoleRequest,
    UpdateWorkspaceRequest,
)
from ee.cloud.workspace.service import WorkspaceService

router = APIRouter(
    prefix="/workspaces", tags=["Workspace"], dependencies=[Depends(require_license)]
)

# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------


@router.post("")
async def create_workspace(
    body: CreateWorkspaceRequest,
    user: User = Depends(current_user),
) -> dict:
    # No workspace yet → no role check possible. Any authenticated user.
    return await WorkspaceService.create(user, body)


@router.get("")
async def list_workspaces(
    user: User = Depends(current_user),
) -> list[dict]:
    return await WorkspaceService.list_for_user(user)


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    user: User = Depends(require_membership),
) -> dict:
    return await WorkspaceService.get(workspace_id, user)


@router.patch("/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    body: UpdateWorkspaceRequest,
    user: User = Depends(require_action("workspace.update")),
) -> dict:
    return await WorkspaceService.update(workspace_id, user, body)


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    user: User = Depends(require_action("workspace.delete")),
) -> Response:
    await WorkspaceService.delete(workspace_id, user)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/members")
async def list_members(
    workspace_id: str,
    user: User = Depends(require_membership),
) -> list[dict]:
    return await WorkspaceService.list_members(workspace_id, user)


@router.patch("/{workspace_id}/members/{user_id}")
async def update_member_role(
    workspace_id: str,
    user_id: str,
    body: UpdateMemberRoleRequest,
    user: User = Depends(require_action("workspace.member.role_change")),
) -> dict:
    await WorkspaceService.update_member_role(workspace_id, user_id, body.role, user)
    return {"ok": True}


@router.delete("/{workspace_id}/members/{user_id}", status_code=204)
async def remove_member(
    workspace_id: str,
    user_id: str,
    user: User = Depends(require_action("workspace.member.remove")),
) -> Response:
    await WorkspaceService.remove_member(workspace_id, user_id, user)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/invites")
async def list_invites(
    workspace_id: str,
    user: User = Depends(require_action("invite.create")),
) -> list[dict]:
    return await WorkspaceService.list_invites(workspace_id)


@router.post("/{workspace_id}/invites")
async def create_invite(
    workspace_id: str,
    body: CreateInviteRequest,
    user: User = Depends(require_action("invite.create")),
) -> dict:
    return await WorkspaceService.create_invite(workspace_id, user, body)


@router.get("/invites/{token}")
async def validate_invite(token: str) -> dict:
    return await WorkspaceService.validate_invite(token)


@router.post("/invites/{token}/accept")
async def accept_invite(
    token: str,
    user: User = Depends(current_user),
) -> dict:
    # Accepting an invite requires only authentication; the invite token
    # itself is the authorization artifact.
    await WorkspaceService.accept_invite(token, user)
    return {"ok": True}


@router.delete("/{workspace_id}/invites/{invite_id}", status_code=204)
async def revoke_invite(
    workspace_id: str,
    invite_id: str,
    user: User = Depends(require_action("invite.revoke")),
) -> Response:
    await WorkspaceService.revoke_invite(workspace_id, invite_id, user)
    return Response(status_code=204)
