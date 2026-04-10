# Automations models — Pydantic models for rule-based pocket automations.
# Created: 2026-03-30 — RuleType enum, Rule, CreateRuleRequest, UpdateRuleRequest.
# Updated: 2026-03-30 — Added ExecutionMode enum, mode/cooldown_minutes/last_evaluated/
#   linked_intention_id fields to Rule, and mode/cooldown_minutes to request models.

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RuleType(str, Enum):
    THRESHOLD = "threshold"
    SCHEDULE = "schedule"
    DATA_CHANGE = "data_change"


class ExecutionMode(str, Enum):
    REQUIRE_APPROVAL = "require_approval"
    AUTO_EXECUTE = "auto_execute"
    NOTIFY_ONLY = "notify_only"


class Rule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    pocket_id: str = ""
    name: str
    description: str = ""
    enabled: bool = True
    type: RuleType
    # Condition fields
    object_type: Optional[str] = None  # "Product", "Order", etc.
    property: Optional[str] = None  # "stock", "revenue", etc.
    operator: Optional[str] = None  # "less_than", "greater_than", "equals", "changed"
    value: Optional[str] = None
    schedule: Optional[str] = None  # cron expression or preset
    # Action
    action: str = ""  # what to do when rule fires
    # Execution
    mode: ExecutionMode = ExecutionMode.REQUIRE_APPROVAL
    cooldown_minutes: int = 60  # don't re-fire within this window
    # Stats
    last_fired: Optional[datetime] = None
    last_evaluated: Optional[datetime] = None
    fire_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # Bridge to core daemon
    linked_intention_id: Optional[str] = None  # core daemon intention ID


class CreateRuleRequest(BaseModel):
    pocket_id: str = ""
    name: str
    description: str = ""
    type: RuleType
    object_type: Optional[str] = None
    property: Optional[str] = None
    operator: Optional[str] = None
    value: Optional[str] = None
    schedule: Optional[str] = None
    action: str = ""
    mode: Optional[ExecutionMode] = None
    cooldown_minutes: Optional[int] = None


class UpdateRuleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    object_type: Optional[str] = None
    property: Optional[str] = None
    operator: Optional[str] = None
    value: Optional[str] = None
    schedule: Optional[str] = None
    action: Optional[str] = None
    mode: Optional[ExecutionMode] = None
    cooldown_minutes: Optional[int] = None
    last_evaluated: Optional[datetime] = None
    linked_intention_id: Optional[str] = None
