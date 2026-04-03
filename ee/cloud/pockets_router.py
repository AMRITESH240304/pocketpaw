"""Pockets CRUD — pockets, widgets, members, agents."""

from __future__ import annotations

import logging
from typing import Any

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ee.cloud.deps import get_optional_workspace_id, get_user_id, get_workspace_id
from ee.cloud.license import require_license
from ee.cloud.models.pocket import Pocket, Widget, WidgetPosition
from ee.cloud.ripple_normalizer import normalize_ripple_spec

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pockets"], dependencies=[Depends(require_license)])

# ---------------------------------------------------------------------------
# Request schemas (camelCase to match frontend)
# ---------------------------------------------------------------------------


class CreatePocketRequest(BaseModel):
    name: str
    description: str = ""
    type: str = "custom"
    icon: str = ""
    color: str = ""
    agents: list[str] | None = None
    rippleSpec: dict[str, Any] | None = None
    visibility: str = "private"


class UpdatePocketRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    type: str | None = None
    icon: str | None = None
    color: str | None = None
    rippleSpec: dict[str, Any] | None = None
    visibility: str | None = None


class AddWidgetRequest(BaseModel):
    name: str
    type: str = "custom"
    icon: str = ""
    color: str = ""
    span: str = "col-span-1"
    dataSourceType: str = "static"
    config: dict[str, Any] = Field(default_factory=dict)
    props: dict[str, Any] = Field(default_factory=dict)
    data: Any = None
    assignedAgent: str | None = None
    row: int = 0
    col: int = 0


class UpdateWidgetRequest(BaseModel):
    name: str | None = None
    type: str | None = None
    icon: str | None = None
    color: str | None = None
    span: str | None = None
    dataSourceType: str | None = None
    config: dict[str, Any] | None = None
    props: dict[str, Any] | None = None
    data: Any = None
    assignedAgent: str | None = None
    row: int | None = None
    col: int | None = None


class MemberRequest(BaseModel):
    userId: str


class AgentRequest(BaseModel):
    agentId: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_pocket(pocket_id: PydanticObjectId, workspace_id: str) -> Pocket:
    pocket = await Pocket.get(pocket_id)
    if not pocket or pocket.workspace != workspace_id:
        raise HTTPException(404, "Pocket not found")
    return pocket


def _find_widget_index(pocket: Pocket, widget_id: str) -> int:
    """Find widget index by _id. Raises 404 if not found."""
    for i, w in enumerate(pocket.widgets):
        if w.id == widget_id:
            return i
    raise HTTPException(404, "Widget not found")


# ---------------------------------------------------------------------------
# Pocket CRUD
# ---------------------------------------------------------------------------


@router.post("/pockets")
async def create_pocket(
    body: CreatePocketRequest,
    workspace_id: str | None = Depends(get_optional_workspace_id),
    user_id: str = Depends(get_user_id),
):
    rippleSpec = normalize_ripple_spec(body.rippleSpec) if body.rippleSpec else None
    pocket = Pocket(
        workspace=workspace_id or "",
        name=body.name,
        description=body.description,
        type=body.type,
        icon=body.icon,
        color=body.color,
        owner=user_id,
        agents=body.agents or [],
        rippleSpec=rippleSpec,
        visibility=body.visibility,
    )
    await pocket.insert()
    return pocket


@router.get("/pockets")
async def list_pockets(
    workspace_id: str | None = Depends(get_optional_workspace_id),
    user_id: str = Depends(get_user_id),
):
    if workspace_id:
        return await Pocket.find(Pocket.workspace == workspace_id).to_list()
    return await Pocket.find(Pocket.owner == user_id).to_list()


@router.get("/pockets/{pocket_id}")
async def get_pocket(
    pocket_id: PydanticObjectId,
    workspace_id: str = Depends(get_workspace_id),
):
    return await _get_pocket(pocket_id, workspace_id)


@router.patch("/pockets/{pocket_id}")
async def update_pocket(
    pocket_id: PydanticObjectId,
    body: UpdatePocketRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    pocket = await _get_pocket(pocket_id, workspace_id)
    updates = body.model_dump(exclude_none=True)
    if "rippleSpec" in updates and updates["rippleSpec"] is not None:
        updates["rippleSpec"] = normalize_ripple_spec(updates["rippleSpec"])
    if updates:
        await pocket.update({"$set": updates})
        await pocket.sync()
    return pocket


@router.delete("/pockets/{pocket_id}")
async def delete_pocket(
    pocket_id: PydanticObjectId,
    workspace_id: str = Depends(get_workspace_id),
):
    pocket = await _get_pocket(pocket_id, workspace_id)
    await pocket.delete()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Widgets (addressed by _id, not index)
# ---------------------------------------------------------------------------


@router.post("/pockets/{pocket_id}/widgets")
async def add_widget(
    pocket_id: PydanticObjectId,
    body: AddWidgetRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    pocket = await _get_pocket(pocket_id, workspace_id)
    widget = Widget(
        name=body.name,
        type=body.type,
        icon=body.icon,
        color=body.color,
        span=body.span,
        dataSourceType=body.dataSourceType,
        config=body.config,
        props=body.props,
        data=body.data,
        assignedAgent=body.assignedAgent,
        position=WidgetPosition(row=body.row, col=body.col),
    )
    pocket.widgets.append(widget)
    await pocket.save()
    return pocket


@router.patch("/pockets/{pocket_id}/widgets/{widget_id}")
async def update_widget(
    pocket_id: PydanticObjectId,
    widget_id: str,
    body: UpdateWidgetRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    pocket = await _get_pocket(pocket_id, workspace_id)
    idx = _find_widget_index(pocket, widget_id)
    updates = body.model_dump(exclude_none=True)
    widget = pocket.widgets[idx]
    for key, val in updates.items():
        if key == "row":
            widget.position.row = val
        elif key == "col":
            widget.position.col = val
        else:
            setattr(widget, key, val)
    await pocket.save()
    return pocket


@router.delete("/pockets/{pocket_id}/widgets/{widget_id}")
async def remove_widget(
    pocket_id: PydanticObjectId,
    widget_id: str,
    workspace_id: str = Depends(get_workspace_id),
):
    pocket = await _get_pocket(pocket_id, workspace_id)
    idx = _find_widget_index(pocket, widget_id)
    pocket.widgets.pop(idx)
    await pocket.save()
    return pocket


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@router.post("/pockets/{pocket_id}/members")
async def add_member(
    pocket_id: PydanticObjectId,
    body: MemberRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    pocket = await _get_pocket(pocket_id, workspace_id)
    if body.userId not in pocket.team:
        pocket.team.append(body.userId)
        await pocket.save()
    return pocket


@router.delete("/pockets/{pocket_id}/members/{user_id}")
async def remove_member(
    pocket_id: PydanticObjectId,
    user_id: str,
    workspace_id: str = Depends(get_workspace_id),
):
    pocket = await _get_pocket(pocket_id, workspace_id)
    pocket.team = [uid for uid in pocket.team if uid != user_id]
    await pocket.save()
    return pocket


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


@router.post("/pockets/{pocket_id}/agents")
async def add_agent(
    pocket_id: PydanticObjectId,
    body: AgentRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    pocket = await _get_pocket(pocket_id, workspace_id)
    if body.agentId not in pocket.agents:
        pocket.agents.append(body.agentId)
        await pocket.save()
    return pocket
