"""Chat domain — group and message business logic."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from beanie import PydanticObjectId

from ee.cloud.chat.schemas import (
    AddGroupAgentRequest,
    CreateGroupRequest,
    EditMessageRequest,
    SendMessageRequest,
    UpdateGroupAgentRequest,
    UpdateGroupRequest,
)
from ee.cloud.models.group import Group, GroupAgent
from ee.cloud.models.message import Attachment, Mention, Message, Reaction
from ee.cloud.shared.errors import Forbidden, NotFound, ValidationError
from ee.cloud.shared.events import event_bus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_slug(name: str) -> str:
    """Lowercase, replace spaces/underscores with hyphens, strip non-alnum."""
    slug = name.lower().strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


def _group_response(group: Group) -> dict:
    """Convert a Group document to a frontend-compatible dict."""
    return {
        "_id": str(group.id),
        "workspace": group.workspace,
        "name": group.name,
        "slug": group.slug,
        "description": group.description,
        "type": group.type,
        "icon": group.icon,
        "color": group.color,
        "owner": group.owner,
        "members": group.members,
        "agents": [a.model_dump() for a in group.agents],
        "pinnedMessages": group.pinned_messages,
        "archived": group.archived,
        "lastMessageAt": group.last_message_at.isoformat() if group.last_message_at else None,
        "messageCount": group.message_count,
        "createdAt": group.createdAt.isoformat() if group.createdAt else None,
    }


def _message_response(msg: Message) -> dict:
    """Convert a Message document to a frontend-compatible dict."""
    return {
        "_id": str(msg.id),
        "group": msg.group,
        "sender": msg.sender,
        "senderType": msg.sender_type,
        "content": msg.content,
        "mentions": [m.model_dump() for m in msg.mentions],
        "replyTo": msg.reply_to,
        "attachments": [a.model_dump() for a in msg.attachments],
        "reactions": [r.model_dump() for r in msg.reactions],
        "edited": msg.edited,
        "editedAt": msg.edited_at.isoformat() if msg.edited_at else None,
        "deleted": msg.deleted,
        "createdAt": msg.createdAt.isoformat() if msg.createdAt else None,
    }


def _require_group_member(group: Group, user_id: str) -> None:
    """Raise Forbidden if user is not a member of the group."""
    if user_id not in group.members:
        raise Forbidden("group.not_member", "You are not a member of this group")


def _require_group_admin(group: Group, user_id: str) -> None:
    """Raise Forbidden if user is not the group owner (admin).

    Groups don't have per-member roles — the owner is the sole admin.
    """
    if group.owner != user_id:
        raise Forbidden("group.not_admin", "Only the group owner can perform this action")


async def _get_group_or_404(group_id: str) -> Group:
    """Load a group by ID or raise NotFound."""
    group = await Group.get(PydanticObjectId(group_id))
    if not group:
        raise NotFound("group", group_id)
    return group


async def _get_message_or_404(message_id: str) -> Message:
    """Load a non-deleted message by ID or raise NotFound."""
    msg = await Message.get(PydanticObjectId(message_id))
    if not msg or msg.deleted:
        raise NotFound("message", message_id)
    return msg


# ---------------------------------------------------------------------------
# GroupService
# ---------------------------------------------------------------------------


class GroupService:
    """Stateless service for group/channel business logic."""

    @staticmethod
    async def create_group(
        workspace_id: str, user_id: str, body: CreateGroupRequest
    ) -> dict:
        """Create a group and add the creator as a member.

        For DMs: validates exactly 2 member_ids, auto-names as "DM".
        """
        if body.type == "dm":
            if len(body.member_ids) != 1:
                raise ValidationError(
                    "group.dm_requires_one_target",
                    "DM groups require exactly one target member_id (the other party)",
                )
            members = sorted({user_id, body.member_ids[0]})
            name = "DM"
        else:
            members = list({user_id, *body.member_ids})
            name = body.name

        slug = _generate_slug(name)

        group = Group(
            workspace=workspace_id,
            name=name,
            slug=slug,
            description=body.description,
            type=body.type,
            icon=body.icon,
            color=body.color,
            members=members,
            owner=user_id,
        )
        await group.insert()
        return _group_response(group)

    @staticmethod
    async def list_groups(workspace_id: str, user_id: str) -> list[dict]:
        """List groups visible to the user.

        Returns public groups in the workspace plus private/dm groups
        where the user is a member.
        """
        groups = await Group.find(
            {
                "workspace": workspace_id,
                "archived": False,
                "$or": [
                    {"type": "public"},
                    {"members": user_id},
                ],
            }
        ).to_list()
        return [_group_response(g) for g in groups]

    @staticmethod
    async def get_group(group_id: str, user_id: str) -> dict:
        """Get a single group. Private/DM groups require membership."""
        group = await _get_group_or_404(group_id)

        if group.type in ("private", "dm"):
            _require_group_member(group, user_id)

        return _group_response(group)

    @staticmethod
    async def update_group(
        group_id: str, user_id: str, body: UpdateGroupRequest
    ) -> dict:
        """Update group fields. Owner only. Cannot update DMs."""
        group = await _get_group_or_404(group_id)

        if group.type == "dm":
            raise Forbidden("group.cannot_update_dm", "DM groups cannot be updated")
        _require_group_admin(group, user_id)

        if body.name is not None:
            group.name = body.name
            group.slug = _generate_slug(body.name)
        if body.description is not None:
            group.description = body.description
        if body.icon is not None:
            group.icon = body.icon
        if body.color is not None:
            group.color = body.color

        await group.save()
        return _group_response(group)

    @staticmethod
    async def archive_group(group_id: str, user_id: str) -> None:
        """Archive a group. Owner only."""
        group = await _get_group_or_404(group_id)
        _require_group_admin(group, user_id)
        group.archived = True
        await group.save()

    @staticmethod
    async def join_group(group_id: str, user_id: str) -> None:
        """Join a public group. Adds user to members list."""
        group = await _get_group_or_404(group_id)

        if group.type != "public":
            raise Forbidden("group.not_public", "Only public groups can be joined directly")
        if group.archived:
            raise Forbidden("group.archived", "Cannot join an archived group")

        if user_id not in group.members:
            group.members.append(user_id)
            await group.save()

    @staticmethod
    async def leave_group(group_id: str, user_id: str) -> None:
        """Leave a group. Owner cannot leave (must transfer ownership first)."""
        group = await _get_group_or_404(group_id)
        _require_group_member(group, user_id)

        if group.owner == user_id:
            raise Forbidden(
                "group.owner_cannot_leave",
                "The group owner cannot leave. Transfer ownership first.",
            )

        group.members.remove(user_id)
        await group.save()

    @staticmethod
    async def add_members(group_id: str, user_id: str, member_ids: list[str]) -> None:
        """Add members to a group. Owner only."""
        group = await _get_group_or_404(group_id)
        _require_group_admin(group, user_id)

        if group.archived:
            raise Forbidden("group.archived", "Cannot modify an archived group")

        added = False
        for mid in member_ids:
            if mid not in group.members:
                group.members.append(mid)
                added = True

        if added:
            await group.save()

    @staticmethod
    async def remove_member(group_id: str, user_id: str, target_user_id: str) -> None:
        """Remove a member from a group. Owner only. Cannot remove the owner."""
        group = await _get_group_or_404(group_id)
        _require_group_admin(group, user_id)

        if target_user_id == group.owner:
            raise Forbidden("group.cannot_remove_owner", "Cannot remove the group owner")

        if target_user_id not in group.members:
            raise NotFound("member", target_user_id)

        group.members.remove(target_user_id)
        await group.save()

    @staticmethod
    async def add_agent(
        group_id: str, user_id: str, body: AddGroupAgentRequest
    ) -> None:
        """Add an agent to a group. Owner only."""
        group = await _get_group_or_404(group_id)
        _require_group_admin(group, user_id)

        # Check if agent is already in the group
        for existing in group.agents:
            if existing.agent == body.agent_id:
                raise ValidationError(
                    "group.agent_already_added",
                    f"Agent '{body.agent_id}' is already in this group",
                )

        group.agents.append(
            GroupAgent(
                agent=body.agent_id,
                role=body.role,
                respond_mode=body.respond_mode,
            )
        )
        await group.save()

    @staticmethod
    async def update_agent(
        group_id: str, user_id: str, agent_id: str, body: UpdateGroupAgentRequest
    ) -> None:
        """Update an agent's respond_mode in a group. Owner only."""
        group = await _get_group_or_404(group_id)
        _require_group_admin(group, user_id)

        for agent in group.agents:
            if agent.agent == agent_id:
                agent.respond_mode = body.respond_mode
                await group.save()
                return

        raise NotFound("agent", agent_id)

    @staticmethod
    async def remove_agent(group_id: str, user_id: str, agent_id: str) -> None:
        """Remove an agent from a group. Owner only."""
        group = await _get_group_or_404(group_id)
        _require_group_admin(group, user_id)

        original_len = len(group.agents)
        group.agents = [a for a in group.agents if a.agent != agent_id]
        if len(group.agents) == original_len:
            raise NotFound("agent", agent_id)

        await group.save()

    @staticmethod
    async def get_or_create_dm(
        workspace_id: str, user_id: str, target_user_id: str
    ) -> dict:
        """Find an existing DM between two users, or create one.

        DM groups have type="dm", sorted members, and name="DM".
        """
        members = sorted([user_id, target_user_id])

        existing = await Group.find_one(
            {
                "workspace": workspace_id,
                "type": "dm",
                "members": {"$all": members, "$size": len(members)},
            }
        )
        if existing:
            return _group_response(existing)

        group = Group(
            workspace=workspace_id,
            name="DM",
            slug=_generate_slug("dm"),
            type="dm",
            members=members,
            owner=user_id,
        )
        await group.insert()
        return _group_response(group)


# ---------------------------------------------------------------------------
# MessageService
# ---------------------------------------------------------------------------


class MessageService:
    """Stateless service for message business logic."""

    @staticmethod
    async def send_message(
        group_id: str, user_id: str, body: SendMessageRequest
    ) -> dict:
        """Send a message to a group.

        Verifies membership, checks group is not archived, creates the
        Message document, emits a ``message.sent`` event, and updates
        the group's last_message_at / message_count.
        """
        group = await _get_group_or_404(group_id)
        _require_group_member(group, user_id)

        if group.archived:
            raise Forbidden("group.archived", "Cannot send messages to an archived group")

        mentions = [Mention(**m) for m in body.mentions]
        attachments = [Attachment(**a) for a in body.attachments]

        msg = Message(
            group=group_id,
            sender=user_id,
            sender_type="user",
            content=body.content,
            mentions=mentions,
            reply_to=body.reply_to,
            attachments=attachments,
        )
        await msg.insert()

        # Update group stats
        group.last_message_at = msg.createdAt
        group.message_count += 1
        await group.save()

        response = _message_response(msg)

        await event_bus.emit(
            "message.sent",
            {
                "group_id": group_id,
                "message_id": str(msg.id),
                "sender_id": user_id,
                "sender_type": "user",
                "content": body.content,
                "mentions": body.mentions,
                "workspace_id": group.workspace,
            },
        )

        return response

    @staticmethod
    async def edit_message(
        message_id: str, user_id: str, body: EditMessageRequest
    ) -> dict:
        """Edit a message. Author only."""
        msg = await _get_message_or_404(message_id)

        if msg.sender != user_id:
            raise Forbidden("message.not_author", "Only the message author can edit it")

        msg.content = body.content
        msg.edited = True
        msg.edited_at = datetime.now(UTC)
        await msg.save()

        return _message_response(msg)

    @staticmethod
    async def delete_message(message_id: str, user_id: str) -> None:
        """Soft-delete a message. Author or group owner can delete."""
        msg = await _get_message_or_404(message_id)

        if msg.sender != user_id:
            # Check if user is the group owner
            group = await _get_group_or_404(msg.group)
            if group.owner != user_id:
                raise Forbidden(
                    "message.not_authorized",
                    "Only the author or group owner can delete this message",
                )

        msg.deleted = True
        await msg.save()

    @staticmethod
    async def toggle_reaction(
        message_id: str, user_id: str, emoji: str
    ) -> dict:
        """Toggle a reaction on a message.

        If the user already reacted with the given emoji, remove their
        reaction. Otherwise, add it. If the emoji reaction has no users
        left, remove the entire reaction entry.
        """
        msg = await _get_message_or_404(message_id)

        # Find existing reaction for this emoji
        existing: Reaction | None = None
        for r in msg.reactions:
            if r.emoji == emoji:
                existing = r
                break

        if existing is not None:
            if user_id in existing.users:
                # Remove user from this reaction
                existing.users.remove(user_id)
                # Remove the reaction entry entirely if no users left
                if not existing.users:
                    msg.reactions.remove(existing)
            else:
                existing.users.append(user_id)
        else:
            msg.reactions.append(Reaction(emoji=emoji, users=[user_id]))

        await msg.save()
        return _message_response(msg)

    @staticmethod
    async def get_messages(
        group_id: str,
        user_id: str,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict:
        """Cursor-based paginated messages, newest first.

        Cursor format: ``"{iso_timestamp}|{object_id}"``.
        Fetches ``limit + 1`` to determine ``has_more``.
        Excludes soft-deleted messages.
        """
        group = await _get_group_or_404(group_id)

        if group.type in ("private", "dm"):
            _require_group_member(group, user_id)

        query: dict = {"group": group_id, "deleted": False}

        if cursor:
            parts = cursor.split("|", 1)
            if len(parts) == 2:
                cursor_time = datetime.fromisoformat(parts[0])
                cursor_id = PydanticObjectId(parts[1])
                query["$or"] = [
                    {"createdAt": {"$lt": cursor_time}},
                    {"createdAt": cursor_time, "_id": {"$lt": cursor_id}},
                ]

        messages = (
            await Message.find(query)
            .sort([("createdAt", -1), ("_id", -1)])
            .limit(limit + 1)
            .to_list()
        )

        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]

        items = [_message_response(m) for m in messages]

        next_cursor: str | None = None
        if has_more and messages:
            last = messages[-1]
            next_cursor = f"{last.createdAt.isoformat()}|{last.id}"

        return {"items": items, "nextCursor": next_cursor, "hasMore": has_more}

    @staticmethod
    async def get_thread(message_id: str, user_id: str) -> list[dict]:
        """Get all replies to a message, sorted ascending by creation time."""
        msg = await _get_message_or_404(message_id)

        # Verify user can access the group
        group = await _get_group_or_404(msg.group)
        if group.type in ("private", "dm"):
            _require_group_member(group, user_id)

        replies = (
            await Message.find({"reply_to": str(msg.id), "deleted": False})
            .sort([("createdAt", 1)])
            .to_list()
        )
        return [_message_response(r) for r in replies]

    @staticmethod
    async def pin_message(group_id: str, user_id: str, message_id: str) -> None:
        """Pin a message in a group. Owner only."""
        group = await _get_group_or_404(group_id)
        _require_group_admin(group, user_id)

        # Verify message belongs to this group
        msg = await _get_message_or_404(message_id)
        if msg.group != group_id:
            raise NotFound("message", message_id)

        if message_id not in group.pinned_messages:
            group.pinned_messages.append(message_id)
            await group.save()

    @staticmethod
    async def unpin_message(group_id: str, user_id: str, message_id: str) -> None:
        """Unpin a message from a group. Owner only."""
        group = await _get_group_or_404(group_id)
        _require_group_admin(group, user_id)

        if message_id not in group.pinned_messages:
            raise NotFound("pinned_message", message_id)

        group.pinned_messages.remove(message_id)
        await group.save()

    @staticmethod
    async def search_messages(
        group_id: str, user_id: str, query: str
    ) -> list[dict]:
        """Search messages by content using regex. Limited to 50 results."""
        group = await _get_group_or_404(group_id)

        if group.type in ("private", "dm"):
            _require_group_member(group, user_id)

        # Escape regex special characters for safe search
        escaped = re.escape(query)
        messages = (
            await Message.find(
                {
                    "group": group_id,
                    "deleted": False,
                    "content": {"$regex": escaped, "$options": "i"},
                }
            )
            .sort([("createdAt", -1)])
            .limit(50)
            .to_list()
        )
        return [_message_response(m) for m in messages]
