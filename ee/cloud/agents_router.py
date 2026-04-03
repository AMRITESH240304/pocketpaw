"""Cloud agents API — discover, CRUD, and listing."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ee.cloud.deps import get_current_user as current_user
from ee.cloud.models.agent import Agent

router = APIRouter(prefix="/agents", tags=["Agents"])


class DiscoverRequest(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=24, ge=1, le=100)
    search: str | None = None
    visibility: str = "public"


class DiscoverResponse(BaseModel):
    agents: list[dict]
    total: int
    page: int
    limit: int


@router.post("/discover")
async def discover_agents(body: DiscoverRequest, _user=Depends(current_user)):
    """Discover agents visible to the current user."""
    query: dict = {}
    if body.visibility:
        query["visibility"] = body.visibility
    if body.search:
        query["name"] = {"$regex": body.search, "$options": "i"}

    total = await Agent.find(query).count()
    skip = (body.page - 1) * body.limit
    agents = await Agent.find(query).skip(skip).limit(body.limit).to_list()

    return DiscoverResponse(
        agents=[a.model_dump(mode="json") for a in agents],
        total=total,
        page=body.page,
        limit=body.limit,
    )


@router.get("")
async def list_agents(
    search: str | None = None,
    limit: int = 50,
    _user=Depends(current_user),
):
    """List agents the user has access to."""
    query: dict = {}
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    agents = await Agent.find(query).limit(limit).to_list()
    return [a.model_dump(mode="json") for a in agents]


@router.get("/{agent_id}")
async def get_agent(agent_id: str, _user=Depends(current_user)):
    """Get a single agent by ID."""
    agent = await Agent.get(agent_id)
    if not agent:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Agent not found")
    return agent.model_dump(mode="json")


@router.get("/uname/{uname}")
async def get_agent_by_uname(uname: str, _user=Depends(current_user)):
    """Get agent by unique name (slug)."""
    agent = await Agent.find_one(Agent.slug == uname)
    if not agent:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Agent not found")
    return agent.model_dump(mode="json")


@router.post("")
async def create_agent(
    data: dict,
    _user=Depends(current_user),
):
    """Create a new agent."""
    agent = Agent(
        workspace=data.get("workspace", "default"),
        name=data["name"],
        slug=data.get("uname", data["name"].lower().replace(" ", "-")),
        owner=str(_user.id),
        visibility=data.get("visibility", "private"),
    )
    await agent.insert()
    return agent.model_dump(mode="json")
