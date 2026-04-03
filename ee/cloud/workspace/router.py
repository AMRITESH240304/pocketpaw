"""Workspace domain — FastAPI router."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from starlette.responses import Response

from ee.cloud.license import require_license
from ee.cloud.models.user import User
from ee.cloud.shared.deps import current_user
from ee.cloud.workspace.schemas import (
    CreateInviteRequest,
    CreateWorkspaceRequest,
    InviteResponse,
    MemberResponse,
    UpdateMemberRoleRequest,
    UpdateWorkspaceRequest,
    WorkspaceResponse,
)
from ee.cloud.workspace.service import WorkspaceService

router = APIRouter(
    prefix="/workspaces", tags=["Workspace"], dependencies=[Depends(require_license)]
)

# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=WorkspaceResponse)
async def create_workspace(
    body: CreateWorkspaceRequest,
    user: User = Depends(current_user),
) -> WorkspaceResponse:
    return await WorkspaceService.create(user, body)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    user: User = Depends(current_user),
) -> list[WorkspaceResponse]:
    return await WorkspaceService.list_for_user(user)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    user: User = Depends(current_user),
) -> WorkspaceResponse:
    return await WorkspaceService.get(workspace_id, user)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    body: UpdateWorkspaceRequest,
    user: User = Depends(current_user),
) -> WorkspaceResponse:
    return await WorkspaceService.update(workspace_id, user, body)


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    user: User = Depends(current_user),
) -> Response:
    await WorkspaceService.delete(workspace_id, user)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/members", response_model=list[MemberResponse])
async def list_members(
    workspace_id: str,
    user: User = Depends(current_user),
) -> list[MemberResponse]:
    return await WorkspaceService.list_members(workspace_id, user)


@router.patch("/{workspace_id}/members/{user_id}")
async def update_member_role(
    workspace_id: str,
    user_id: str,
    body: UpdateMemberRoleRequest,
    user: User = Depends(current_user),
) -> dict:
    await WorkspaceService.update_member_role(workspace_id, user_id, body.role, user)
    return {"ok": True}


@router.delete("/{workspace_id}/members/{user_id}", status_code=204)
async def remove_member(
    workspace_id: str,
    user_id: str,
    user: User = Depends(current_user),
) -> Response:
    await WorkspaceService.remove_member(workspace_id, user_id, user)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/invites", response_model=InviteResponse)
async def create_invite(
    workspace_id: str,
    body: CreateInviteRequest,
    user: User = Depends(current_user),
) -> InviteResponse:
    return await WorkspaceService.create_invite(workspace_id, user, body)


@router.get("/invites/{token}", response_model=InviteResponse)
async def validate_invite(token: str) -> InviteResponse:
    return await WorkspaceService.validate_invite(token)


@router.post("/invites/{token}/accept")
async def accept_invite(
    token: str,
    user: User = Depends(current_user),
) -> dict:
    await WorkspaceService.accept_invite(token, user)
    return {"ok": True}


@router.delete("/{workspace_id}/invites/{invite_id}", status_code=204)
async def revoke_invite(
    workspace_id: str,
    invite_id: str,
    user: User = Depends(current_user),
) -> Response:
    await WorkspaceService.revoke_invite(workspace_id, invite_id, user)
    return Response(status_code=204)
