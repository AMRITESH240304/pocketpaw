"""Sessions CRUD — standalone + pocket-scoped sessions."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime

import httpx
from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ee.cloud.deps import get_optional_workspace_id, get_user_id, get_workspace_id
from ee.cloud.license import require_license
from ee.cloud.models.session import Session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Sessions"], dependencies=[Depends(require_license)])

_RUNTIME_URL = os.environ.get("RUNTIME_URL", "http://localhost:8888")
_RUNTIME_SECRET = os.environ.get("RUNTIME_API_SECRET", "")


def _runtime_headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if _RUNTIME_SECRET:
        h["Authorization"] = f"Bearer {_RUNTIME_SECRET}"
    return h


def _generate_session_id() -> str:
    return f"websocket_{secrets.token_hex(6)}"


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    title: str = "New Chat"


class UpdateSessionRequest(BaseModel):
    title: str | None = None
    pocket: str | None = None  # pocket ID to claim, or explicit None to unclaim

    class Config:
        # Allow null to be explicitly passed for pocket (unclaim)
        json_schema_extra = {"examples": [{"title": "Renamed", "pocket": None}]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_session(session_id: PydanticObjectId) -> Session:
    session = await Session.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session


# ---------------------------------------------------------------------------
# Standalone sessions
# ---------------------------------------------------------------------------


@router.post("/sessions")
async def cloud_create_session(
    body: CreateSessionRequest,
    workspace_id: str | None = Depends(get_optional_workspace_id),
    user_id: str = Depends(get_user_id),
):
    session = Session(
        sessionId=_generate_session_id(),
        pocket=None,
        workspace=workspace_id or "",
        owner=user_id,
        title=body.title,
    )
    await session.insert()
    return session


@router.get("/sessions")
async def cloud_list_sessions(
    workspace_id: str | None = Depends(get_optional_workspace_id),
    user_id: str = Depends(get_user_id),
    pocket: str | None = Query(None, description="Filter by pocket ID, or 'none' for standalone"),
    limit: int = Query(50, ge=1, le=200),
):
    filt: dict = {"owner": user_id}
    if workspace_id:
        filt["workspace"] = workspace_id
    if pocket == "none":
        filt["pocket"] = None
    elif pocket:
        filt["pocket"] = pocket
    return await Session.find(filt).sort(-Session.lastActivity).limit(limit).to_list()


@router.get("/sessions/{session_id}")
async def cloud_get_session(session_id: PydanticObjectId):
    return await _get_session(session_id)


@router.get("/sessions/{session_id}/history")
async def cloud_get_session_history(
    session_id: PydanticObjectId,
    limit: int = Query(100, ge=1, le=500),
):
    """Proxy message history from the Python runtime."""
    session = await _get_session(session_id)
    url = f"{_RUNTIME_URL}/api/v1/sessions/{session.sessionId}/history?limit={limit}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=_runtime_headers(), timeout=10)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch history from runtime: %s", exc)
        raise HTTPException(502, "Could not fetch session history from runtime")


@router.patch("/sessions/{session_id}")
async def cloud_update_session(
    session_id: PydanticObjectId,
    body: UpdateSessionRequest,
):
    session = await _get_session(session_id)
    updates: dict = {}
    if body.title is not None:
        updates["title"] = body.title
    # pocket can be explicitly set to None (unclaim) or to a string (claim)
    if "pocket" in body.model_fields_set:
        updates["pocket"] = body.pocket
    if updates:
        await session.update({"$set": updates})
        await session.sync()
    return session


@router.delete("/sessions/{session_id}")
async def delete_cloud_session(session_id: PydanticObjectId):
    session = await _get_session(session_id)
    # Best-effort: tell Python to purge messages
    try:
        async with httpx.AsyncClient() as client:
            await client.delete(
                f"{_RUNTIME_URL}/api/v1/sessions/{session.sessionId}",
                headers=_runtime_headers(),
                timeout=5,
            )
    except Exception:
        logger.debug("Failed to purge runtime session %s", session.sessionId, exc_info=True)
    await session.delete()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Pocket-scoped sessions
# ---------------------------------------------------------------------------


@router.get("/pockets/{pocket_id}/sessions")
async def list_pocket_sessions(
    pocket_id: str,
    workspace_id: str = Depends(get_workspace_id),
    limit: int = Query(50, ge=1, le=200),
):
    return (
        await Session.find(
            Session.workspace == workspace_id,
            Session.pocket == pocket_id,
        )
        .sort(-Session.lastActivity)
        .limit(limit)
        .to_list()
    )


@router.post("/pockets/{pocket_id}/sessions")
async def create_pocket_session(
    pocket_id: str,
    body: CreateSessionRequest,
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
):
    session = Session(
        sessionId=_generate_session_id(),
        pocket=pocket_id,
        workspace=workspace_id,
        owner=user_id,
        title=body.title,
    )
    await session.insert()
    return session


# ---------------------------------------------------------------------------
# Touch (called by runtime gateway after each chat message)
# ---------------------------------------------------------------------------


async def touch_session(session_id: str) -> None:
    """Increment message count and update lastActivity. Fire-and-forget."""
    await Session.find_one(Session.sessionId == session_id).update(
        {"$set": {"lastActivity": datetime.now(UTC)}, "$inc": {"messageCount": 1}}
    )
