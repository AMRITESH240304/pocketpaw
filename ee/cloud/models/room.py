"""Room document — membership + link to Python session."""

from __future__ import annotations

from beanie import Document, Indexed
from pydantic import Field


class Room(Document):
    """Chat room with agent and member tracking."""

    workspace: Indexed(str)  # type: ignore[valid-type]
    type: str = Field(pattern="^(dm|group)$")
    name: str = ""
    members: list[str] = Field(default_factory=list)  # User IDs
    agent: str | None = None  # Agent ID
    python_session_id: str = ""  # Links to Python session execution

    class Settings:
        name = "rooms"
