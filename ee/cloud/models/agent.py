"""Agent configuration document."""

from __future__ import annotations

from beanie import Indexed

from ee.cloud.models.base import TimestampedDocument
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    backend: str = "claude_agent_sdk"
    model: str = "claude-sonnet-4-5-20250514"
    system_prompt: str = ""
    tools: list[str] = Field(default_factory=list)
    trust_level: int = Field(default=3, ge=1, le=5)
    soul_path: str = ""
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1)


class Agent(TimestampedDocument):
    """Agent configuration (not execution — config only)."""

    workspace: Indexed(str)  # type: ignore[valid-type]
    name: str
    slug: str
    avatar: str = ""
    config: AgentConfig = Field(default_factory=AgentConfig)
    visibility: str = Field(default="private", pattern="^(private|workspace)$")
    owner: str  # User ID

    class Settings:
        name = "agents"
        indexes = [
            [("workspace", 1), ("slug", 1)],
        ]
