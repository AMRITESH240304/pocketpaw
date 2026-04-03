"""Invite document — workspace membership invitations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from beanie import Document, Indexed
from pydantic import Field


def _default_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=7)


class Invite(Document):
    """Workspace invitation sent to an email address."""

    workspace: Indexed(str)  # type: ignore[valid-type]
    email: Indexed(str)  # type: ignore[valid-type]
    role: str = Field(default="member", pattern="^(admin|member|viewer)$")
    invited_by: str  # User ID
    token: Indexed(str, unique=True)  # type: ignore[valid-type]
    accepted: bool = False
    expires_at: datetime = Field(default_factory=_default_expiry)

    @property
    def expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at

    class Settings:
        name = "invites"
