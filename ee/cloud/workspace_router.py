"""Workspace management + invite flow."""

from __future__ import annotations

import logging
import os
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from ee.cloud.deps import get_user_id, get_workspace_id
from ee.cloud.license import require_license
from ee.cloud.models.invite import Invite
from ee.cloud.models.user import User, WorkspaceMembership
from ee.cloud.models.workspace import Workspace, WorkspaceSettings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Workspace"], dependencies=[Depends(require_license)])


# ---------------------------------------------------------------------------
# Email helper — sends invite via SMTP if configured, returns False otherwise
# ---------------------------------------------------------------------------

async def _send_invite_email(
    to: str,
    workspace_name: str,
    invite_link: str,
    inviter_id: str,
) -> bool:
    """Send invite email via SMTP. Returns True if sent, False if SMTP not configured."""
    smtp_host = os.environ.get("SMTP_HOST", "")
    if not smtp_host:
        return False

    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user or f"noreply@{smtp_host}")
    smtp_tls = os.environ.get("SMTP_TLS", "true").lower() in ("true", "1", "yes")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"You're invited to {workspace_name} on PocketPaw"
    msg["From"] = smtp_from
    msg["To"] = to

    text = (
        f"You've been invited to join {workspace_name} on PocketPaw.\n\n"
        f"Click here to accept: {invite_link}\n\n"
        f"This link expires in 7 days."
    )
    html = f"""\
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; padding: 32px 20px;">
      <h2 style="margin: 0 0 8px; font-size: 20px; color: #111;">Join {workspace_name}</h2>
      <p style="color: #555; font-size: 14px; line-height: 1.5; margin: 0 0 24px;">
        You've been invited to join <strong>{workspace_name}</strong> on PocketPaw.
      </p>
      <a href="{invite_link}" style="display: inline-block; background: #0A84FF; color: white; padding: 10px 24px; border-radius: 8px; text-decoration: none; font-size: 14px; font-weight: 500;">
        Accept Invite
      </a>
      <p style="color: #999; font-size: 12px; margin-top: 24px;">This link expires in 7 days.</p>
    </div>
    """

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        if smtp_tls:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_from, to, msg.as_string())
        server.quit()
        logger.info("Invite email sent to %s", to)
        return True
    except Exception as exc:
        logger.warning("SMTP send failed: %s", exc)
        return False

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CreateWorkspaceRequest(BaseModel):
    name: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$")


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    settings: WorkspaceSettings | None = None


class UpdateMemberRoleRequest(BaseModel):
    role: str = Field(pattern="^(admin|member|viewer)$")


class CreateInviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="member", pattern="^(admin|member|viewer)$")
    group: str | None = None  # Group ID — auto-add user to this group on accept


class AcceptInviteRequest(BaseModel):
    token: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_admin(workspace_id: str, user_id: str) -> None:
    """Raise 403 if user is not owner or admin of the workspace.

    Until auth is fully wired, falls back to checking if user is the workspace owner.
    """
    try:
        user = await User.get(PydanticObjectId(user_id))
        if user:
            membership = next((w for w in user.workspaces if w.workspace == workspace_id), None)
            if not membership or membership.role not in ("owner", "admin"):
                raise HTTPException(403, "Admin access required")
            return
    except Exception:
        pass
    # Fallback: check workspace ownership directly
    ws = await Workspace.get(PydanticObjectId(workspace_id))
    if not ws or ws.owner != user_id:
        raise HTTPException(403, "Admin access required")


# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------


@router.post("/workspace")
async def create_workspace(
    body: CreateWorkspaceRequest,
    user_id: str = Depends(get_user_id),
):
    """Create a new workspace. The creating user becomes the owner."""
    existing = await Workspace.find_one(Workspace.slug == body.slug)
    if existing:
        raise HTTPException(409, "Workspace slug already taken")

    workspace = Workspace(
        name=body.name,
        slug=body.slug,
        owner=user_id,
    )
    await workspace.insert()

    # Add owner membership to user (if user exists in DB — may not exist yet before auth is wired)
    try:
        user = await User.get(PydanticObjectId(user_id))
        if user:
            user.workspaces.append(WorkspaceMembership(workspace=str(workspace.id), role="owner"))
            user.active_workspace = str(workspace.id)
            await user.save()
    except Exception:
        pass  # User not in DB yet — membership will be set up when auth is wired

    return workspace


@router.get("/workspace")
async def get_workspace(workspace_id: str = Depends(get_workspace_id)):
    """Get current workspace info."""
    ws = await Workspace.get(PydanticObjectId(workspace_id))
    if not ws:
        raise HTTPException(404, "Workspace not found")
    return ws


@router.patch("/workspace")
async def update_workspace(
    body: UpdateWorkspaceRequest,
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
):
    """Update workspace settings. Admin+ only."""
    await _require_admin(workspace_id, user_id)
    ws = await Workspace.get(PydanticObjectId(workspace_id))
    if not ws:
        raise HTTPException(404, "Workspace not found")
    updates = body.model_dump(exclude_none=True)
    if updates:
        await ws.update({"$set": updates})
        await ws.sync()
    return ws


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@router.get("/workspace/members")
async def list_members(workspace_id: str = Depends(get_workspace_id)):
    """List all members of the current workspace."""
    users = await User.find({"workspaces.workspace": workspace_id}).to_list()
    members = []
    for u in users:
        membership = next((w for w in u.workspaces if w.workspace == workspace_id), None)
        if membership:
            members.append({
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "avatar": u.avatar,
                "role": membership.role,
                "joined_at": membership.joined_at.isoformat(),
                "status": u.status,
                "last_seen": u.last_seen.isoformat(),
            })
    return members


@router.patch("/workspace/members/{uid}")
async def update_member_role(
    uid: str,
    body: UpdateMemberRoleRequest,
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
):
    """Change a member's role. Admin+ only. Cannot change owner."""
    await _require_admin(workspace_id, user_id)
    target = await User.get(PydanticObjectId(uid))
    if not target:
        raise HTTPException(404, "User not found")
    membership = next((w for w in target.workspaces if w.workspace == workspace_id), None)
    if not membership:
        raise HTTPException(404, "User is not a member of this workspace")
    if membership.role == "owner":
        raise HTTPException(403, "Cannot change owner role")
    membership.role = body.role
    await target.save()
    return {"ok": True, "role": body.role}


@router.delete("/workspace/members/{uid}")
async def remove_member(
    uid: str,
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
):
    """Remove a member from the workspace. Admin+ only. Cannot remove owner."""
    await _require_admin(workspace_id, user_id)
    if uid == user_id:
        raise HTTPException(400, "Cannot remove yourself")
    target = await User.get(PydanticObjectId(uid))
    if not target:
        raise HTTPException(404, "User not found")
    membership = next((w for w in target.workspaces if w.workspace == workspace_id), None)
    if not membership:
        raise HTTPException(404, "User is not a member")
    if membership.role == "owner":
        raise HTTPException(403, "Cannot remove workspace owner")
    target.workspaces = [w for w in target.workspaces if w.workspace != workspace_id]
    if target.active_workspace == workspace_id:
        target.active_workspace = target.workspaces[0].workspace if target.workspaces else None
    await target.save()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------


@router.post("/invites")
async def create_invite(
    body: CreateInviteRequest,
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
):
    """Create an invite. Admin+ only. Checks seat limits."""
    await _require_admin(workspace_id, user_id)

    # Check seat limit
    ws = await Workspace.get(PydanticObjectId(workspace_id))
    if not ws:
        raise HTTPException(404, "Workspace not found")
    member_count = await User.find({"workspaces.workspace": workspace_id}).count()
    pending_count = await Invite.find(
        Invite.workspace == workspace_id, Invite.accepted == False
    ).count()
    if member_count + pending_count >= ws.seats:
        raise HTTPException(
            403, f"Seat limit reached ({ws.seats}). Upgrade your plan for more seats."
        )

    # Check for existing pending invite
    existing = await Invite.find_one(
        Invite.workspace == workspace_id,
        Invite.email == body.email,
        Invite.accepted == False,
    )
    if existing and not existing.expired:
        raise HTTPException(409, "Invite already pending for this email")

    invite = Invite(
        workspace=workspace_id,
        email=body.email,
        role=body.role,
        invited_by=user_id,
        token=secrets.token_urlsafe(32),
        group=body.group,
    )
    await invite.insert()

    # Build invite link
    app_url = os.environ.get("APP_URL", "http://localhost:1420")
    invite_link = f"{app_url}/invite/{invite.token}"

    # Try sending email if SMTP is configured
    email_sent = False
    try:
        email_sent = await _send_invite_email(
            to=body.email,
            workspace_name=ws.name,
            invite_link=invite_link,
            inviter_id=user_id,
        )
    except Exception as exc:
        logger.debug("Email send failed (SMTP not configured?): %s", exc)

    return {
        "_id": str(invite.id),
        "email": invite.email,
        "role": invite.role,
        "token": invite.token,
        "invite_link": invite_link,
        "email_sent": email_sent,
        "expires_at": invite.expires_at.isoformat(),
    }


@router.get("/invites")
async def list_invites(
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
):
    """List pending invites. Admin+ only."""
    await _require_admin(workspace_id, user_id)
    return await Invite.find(
        Invite.workspace == workspace_id, Invite.accepted == False
    ).to_list()


@router.delete("/invites/{invite_id}")
async def revoke_invite(
    invite_id: PydanticObjectId,
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
):
    """Revoke a pending invite. Admin+ only."""
    await _require_admin(workspace_id, user_id)
    invite = await Invite.get(invite_id)
    if not invite or invite.workspace != workspace_id:
        raise HTTPException(404, "Invite not found")
    await invite.delete()
    return {"ok": True}


@router.get("/invites/validate/{token}")
async def validate_invite(token: str):
    """Validate an invite token. Public endpoint (no auth required)."""
    invite = await Invite.find_one(Invite.token == token)
    if not invite:
        raise HTTPException(404, "Invalid invite token")
    if invite.accepted:
        raise HTTPException(410, "Invite already accepted")
    if invite.expired:
        raise HTTPException(410, "Invite has expired")
    ws = await Workspace.get(PydanticObjectId(invite.workspace))

    # Resolve group name if invite is group-scoped
    group_name = None
    if invite.group:
        try:
            from ee.cloud.models.group import Group
            grp = await Group.get(PydanticObjectId(invite.group))
            group_name = grp.name if grp else None
        except Exception:
            pass

    return {
        "valid": True,
        "email": invite.email,
        "role": invite.role,
        "workspace_name": ws.name if ws else "Unknown",
        "group": invite.group,
        "group_name": group_name,
    }


@router.post("/invites/accept")
async def accept_invite(
    body: AcceptInviteRequest,
    user_id: str = Depends(get_user_id),
):
    """Accept an invite. Adds user to workspace."""
    invite = await Invite.find_one(Invite.token == body.token)
    if not invite:
        raise HTTPException(404, "Invalid invite token")
    if invite.accepted:
        raise HTTPException(410, "Invite already accepted")
    if invite.expired:
        raise HTTPException(410, "Invite has expired")

    user = await User.get(PydanticObjectId(user_id))
    if not user:
        raise HTTPException(404, "User not found")

    # Check not already a member
    already = next((w for w in user.workspaces if w.workspace == invite.workspace), None)
    if already:
        invite.accepted = True
        await invite.save()
        return {"ok": True, "workspace": invite.workspace, "already_member": True}

    # Add workspace membership
    user.workspaces.append(
        WorkspaceMembership(workspace=invite.workspace, role=invite.role)
    )
    if not user.active_workspace:
        user.active_workspace = invite.workspace
    await user.save()

    # Auto-add to group if invite was group-scoped
    group_id = invite.group
    if group_id:
        try:
            from ee.cloud.models.group import Group
            grp = await Group.get(PydanticObjectId(group_id))
            if grp and user_id not in grp.members:
                grp.members.append(user_id)
                await grp.save()
        except Exception as exc:
            logger.warning("Failed to auto-add user to group %s: %s", group_id, exc)

    invite.accepted = True
    await invite.save()

    return {"ok": True, "workspace": invite.workspace, "group": group_id}
