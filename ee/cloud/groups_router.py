"""Groups CRUD — channels, members, agents, messages."""

from __future__ import annotations

import logging
from typing import Any

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ee.cloud.deps import get_optional_workspace_id, get_user_id
from ee.cloud.license import require_license
from ee.cloud.models.group import Group, GroupAgent
from ee.cloud.models.message import Attachment, Mention, Message, Reaction

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Groups"], dependencies=[Depends(require_license)])

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CreateGroupRequest(BaseModel):
    name: str
    slug: str = ""
    description: str = ""
    icon: str = ""
    color: str = ""
    type: str = "public"


class UpdateGroupRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    type: str | None = None
    archived: bool | None = None


class AddAgentRequest(BaseModel):
    agent: str  # Agent ID
    role: str = "assistant"
    respond_mode: str = "mention_only"


class UpdateAgentRequest(BaseModel):
    role: str | None = None
    respond_mode: str | None = None


class SendMessageRequest(BaseModel):
    content: str
    mentions: list[Mention] = Field(default_factory=list)
    reply_to: str | None = None
    attachments: list[Attachment] = Field(default_factory=list)


class EditMessageRequest(BaseModel):
    content: str


class ReactRequest(BaseModel):
    emoji: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_group(group_id: PydanticObjectId) -> Group:
    group = await Group.get(group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    return group


async def _require_member(group: Group, user_id: str) -> None:
    """Raise 403 if user is not a member of the group (public groups allow read but not write)."""
    if user_id not in group.members:
        raise HTTPException(403, "You are not a member of this group")


async def _require_not_archived(group: Group) -> None:
    """Raise 410 if group is archived."""
    if group.archived:
        raise HTTPException(410, "This group has been archived")


async def _get_message(message_id: PydanticObjectId) -> Message:
    msg = await Message.get(message_id)
    if not msg or msg.deleted:
        raise HTTPException(404, "Message not found")
    return msg


MAX_MESSAGE_LENGTH = 10_000  # characters


async def _populate_group(group: Group) -> dict:
    """Return group dict with members populated as {_id, name, email} objects."""
    from ee.cloud.models.user import User

    data = group.model_dump(mode="json")
    data["_id"] = str(group.id)

    # Populate members: resolve user IDs to user objects
    populated_members = []
    for uid in group.members:
        try:
            user = await User.get(PydanticObjectId(uid))
            if user:
                populated_members.append({
                    "_id": str(user.id),
                    "name": user.full_name or user.email,
                    "email": user.email,
                })
            else:
                populated_members.append({"_id": uid, "name": uid, "email": ""})
        except Exception:
            populated_members.append({"_id": uid, "name": uid, "email": ""})
    data["members"] = populated_members

    return data


# ---------------------------------------------------------------------------
# Group CRUD
# ---------------------------------------------------------------------------


@router.post("/groups")
async def create_group(
    body: CreateGroupRequest,
    workspace_id: str | None = Depends(get_optional_workspace_id),
    user_id: str = Depends(get_user_id),
):
    slug = body.slug or body.name.lower().replace(" ", "-")
    group = Group(
        workspace=workspace_id or "",
        name=body.name,
        slug=slug,
        description=body.description,
        icon=body.icon,
        color=body.color,
        type=body.type,
        members=[user_id],
        owner=user_id,
    )
    await group.insert()
    return await _populate_group(group)


@router.get("/groups")
async def list_groups(
    workspace_id: str | None = Depends(get_optional_workspace_id),
    user_id: str = Depends(get_user_id),
):
    """List public groups + private groups where user is a member."""
    if workspace_id:
        public = await Group.find(
            Group.workspace == workspace_id,
            Group.type == "public",
            Group.archived == False,
        ).to_list()
        private = await Group.find(
            Group.workspace == workspace_id,
            Group.type == "private",
            Group.members == user_id,
            Group.archived == False,
        ).to_list()
    else:
        public = await Group.find(
            Group.type == "public", Group.archived == False
        ).to_list()
        private = await Group.find(
            Group.type == "private",
            Group.members == user_id,
            Group.archived == False,
        ).to_list()
    seen = {str(g.id) for g in public}
    all_groups = public + [g for g in private if str(g.id) not in seen]
    return [await _populate_group(g) for g in all_groups]


@router.get("/groups/{group_id}")
async def get_group(
    group_id: PydanticObjectId,
    user_id: str = Depends(get_user_id),
):
    group = await _get_group(group_id)
    if group.type == "private" and user_id not in group.members:
        raise HTTPException(403, "You don't have access to this private group")
    return await _populate_group(group)


@router.patch("/groups/{group_id}")
async def update_group(
    group_id: PydanticObjectId,
    body: UpdateGroupRequest,
    user_id: str = Depends(get_user_id),
):
    group = await _get_group(group_id)
    updates = body.model_dump(exclude_none=True)
    if updates:
        await group.update({"$set": updates})
        await group.sync()
    return await _populate_group(group)


@router.delete("/groups/{group_id}")
async def archive_group(
    group_id: PydanticObjectId,
    user_id: str = Depends(get_user_id),
):
    group = await _get_group(group_id)
    if group.owner != user_id:
        raise HTTPException(403, "Only the group owner can archive")
    group.archived = True
    await group.save()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


@router.post("/groups/{group_id}/join")
async def join_group(
    group_id: PydanticObjectId,
    user_id: str = Depends(get_user_id),
):
    group = await _get_group(group_id)
    if group.type != "public":
        raise HTTPException(403, "Cannot join a private group — ask the owner to add you")
    if user_id not in group.members:
        group.members.append(user_id)
        await group.save()
    return await _populate_group(group)


@router.post("/groups/{group_id}/leave")
async def leave_group(
    group_id: PydanticObjectId,
    user_id: str = Depends(get_user_id),
):
    group = await _get_group(group_id)
    if group.owner == user_id:
        raise HTTPException(400, "Owner cannot leave — transfer ownership or archive the group")
    group.members = [m for m in group.members if m != user_id]
    await group.save()
    return {"ok": True}


@router.post("/groups/{group_id}/members")
async def add_member(
    group_id: PydanticObjectId,
    body: BaseModel,
    user_id: str = Depends(get_user_id),
):
    group = await _get_group(group_id)
    target = getattr(body, "user_id", None) or getattr(body, "userId", None)
    if not target:
        raise HTTPException(422, "user_id required")
    if target not in group.members:
        group.members.append(target)
        await group.save()
    return await _populate_group(group)


@router.delete("/groups/{group_id}/members/{uid}")
async def remove_member(
    group_id: PydanticObjectId,
    uid: str,
    user_id: str = Depends(get_user_id),
):
    group = await _get_group(group_id)
    if uid == group.owner:
        raise HTTPException(403, "Cannot remove the group owner")
    # Only owner or the user themselves can remove
    if user_id != group.owner and user_id != uid:
        raise HTTPException(403, "Only the group owner can remove members")
    group.members = [m for m in group.members if m != uid]
    await group.save()
    return await _populate_group(group)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


@router.post("/groups/{group_id}/agents")
async def add_agent(
    group_id: PydanticObjectId,
    body: AddAgentRequest,
):
    group = await _get_group(group_id)
    # Replace if already exists
    group.agents = [a for a in group.agents if a.agent != body.agent]
    group.agents.append(GroupAgent(
        agent=body.agent,
        role=body.role,
        respond_mode=body.respond_mode,
    ))
    await group.save()
    return await _populate_group(group)


@router.patch("/groups/{group_id}/agents/{agent_id}")
async def update_agent_mode(
    group_id: PydanticObjectId,
    agent_id: str,
    body: UpdateAgentRequest,
):
    group = await _get_group(group_id)
    agent = next((a for a in group.agents if a.agent == agent_id), None)
    if not agent:
        raise HTTPException(404, "Agent not in this group")
    if body.role is not None:
        agent.role = body.role
    if body.respond_mode is not None:
        agent.respond_mode = body.respond_mode
    await group.save()
    return await _populate_group(group)


@router.delete("/groups/{group_id}/agents/{agent_id}")
async def remove_agent(
    group_id: PydanticObjectId,
    agent_id: str,
):
    group = await _get_group(group_id)
    group.agents = [a for a in group.agents if a.agent != agent_id]
    await group.save()
    return await _populate_group(group)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@router.get("/groups/{group_id}/messages")
async def list_messages(
    group_id: PydanticObjectId,
    user_id: str = Depends(get_user_id),
    before: str | None = Query(None, description="Cursor: message _id to load before"),
    limit: int = Query(50, ge=1, le=200),
):
    group = await _get_group(group_id)
    if group.type == "private":
        await _require_member(group, user_id)
    filt: dict[str, Any] = {"group": str(group_id), "deleted": False}
    if before:
        filt["_id"] = {"$lt": PydanticObjectId(before)}
    return (
        await Message.find(filt)
        .sort(-Message.id)
        .limit(limit)
        .to_list()
    )


@router.post("/groups/{group_id}/messages")
async def send_message(
    group_id: PydanticObjectId,
    body: SendMessageRequest,
    user_id: str = Depends(get_user_id),
):
    group = await _get_group(group_id)
    await _require_not_archived(group)
    await _require_member(group, user_id)

    content = body.content.strip()
    if not content:
        raise HTTPException(422, "Message content cannot be empty")
    if len(content) > MAX_MESSAGE_LENGTH:
        raise HTTPException(422, f"Message too long (max {MAX_MESSAGE_LENGTH} characters)")

    msg = Message(
        group=str(group_id),
        sender=user_id,
        sender_type="user",
        content=content,
        mentions=body.mentions,
        reply_to=body.reply_to,
        attachments=body.attachments,
    )
    await msg.insert()
    return msg


@router.patch("/groups/{group_id}/messages/{message_id}")
async def edit_message(
    group_id: PydanticObjectId,
    message_id: PydanticObjectId,
    body: EditMessageRequest,
    user_id: str = Depends(get_user_id),
):
    group = await _get_group(group_id)
    await _require_not_archived(group)
    msg = await _get_message(message_id)
    if msg.sender != user_id:
        raise HTTPException(403, "Can only edit your own messages")
    content = body.content.strip()
    if not content:
        raise HTTPException(422, "Message content cannot be empty")
    if len(content) > MAX_MESSAGE_LENGTH:
        raise HTTPException(422, f"Message too long (max {MAX_MESSAGE_LENGTH} characters)")
    msg.content = content
    msg.edited = True
    await msg.save()
    return msg


@router.delete("/groups/{group_id}/messages/{message_id}")
async def delete_message(
    group_id: PydanticObjectId,
    message_id: PydanticObjectId,
    user_id: str = Depends(get_user_id),
):
    group = await _get_group(group_id)
    await _require_not_archived(group)
    msg = await _get_message(message_id)
    # Owner can delete any message, others can only delete their own
    if msg.sender != user_id and group.owner != user_id:
        raise HTTPException(403, "Can only delete your own messages")
    msg.deleted = True
    await msg.save()
    return {"ok": True}


@router.post("/groups/{group_id}/messages/{message_id}/react")
async def react_to_message(
    group_id: PydanticObjectId,
    message_id: PydanticObjectId,
    body: ReactRequest,
    user_id: str = Depends(get_user_id),
):
    msg = await _get_message(message_id)
    existing = next((r for r in msg.reactions if r.emoji == body.emoji), None)
    if existing:
        if user_id in existing.users:
            existing.users.remove(user_id)  # Toggle off
            if not existing.users:
                msg.reactions = [r for r in msg.reactions if r.emoji != body.emoji]
        else:
            existing.users.append(user_id)  # Toggle on
    else:
        msg.reactions.append(Reaction(emoji=body.emoji, users=[user_id]))
    await msg.save()
    return msg


@router.get("/groups/{group_id}/messages/search")
async def search_messages(
    group_id: PydanticObjectId,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
):
    return (
        await Message.find(
            Message.group == str(group_id),
            Message.deleted == False,
            {"$text": {"$search": q}},
        )
        .limit(limit)
        .to_list()
    )
