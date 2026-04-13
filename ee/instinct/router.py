# ee/instinct/router.py — FastAPI router for the Instinct decision pipeline API.
# Created: 2026-03-28 — Propose, approve/reject, list pending, query audit.
# Updated: 2026-03-30 — Added GET /instinct/actions (list all with status filter),
#   GET /instinct/audit/export (JSON export), switched to singleton from ee.api.
# Updated: 2026-04-12 (Move 1 PR-A) — /approve now accepts optional edited fields.
#   When present, the server diffs the stored proposal against the edits, persists
#   a Correction, then approves. GET /instinct/corrections exposes corrections
#   scoped to a pocket or an action so the UI and agents can read them back.

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ee.instinct.correction import (
    Correction,
    compute_patches,
    summarize_correction,
)
from ee.instinct.models import (
    Action,
    ActionCategory,
    ActionPriority,
    ActionStatus,
    ActionTrigger,
    AuditEntry,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Instinct"])


def _store():
    from ee.api import get_instinct_store

    return get_instinct_store()


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ProposeRequest(BaseModel):
    pocket_id: str
    title: str
    description: str = ""
    recommendation: str = ""
    trigger: ActionTrigger
    category: ActionCategory = ActionCategory.WORKFLOW
    priority: ActionPriority = ActionPriority.MEDIUM
    parameters: dict[str, Any] = {}


class RejectRequest(BaseModel):
    reason: str = ""


class ApproveRequest(BaseModel):
    """Optional edits and approver metadata for an approval.

    When any of `title`, `description`, `recommendation`, `category`, `priority`,
    or `parameters` differ from the stored proposal, the server computes a
    Correction before approving. Omit the fields to approve unchanged.
    """

    approver: str = "user"
    title: str | None = None
    description: str | None = None
    recommendation: str | None = None
    category: ActionCategory | None = None
    priority: ActionPriority | None = None
    parameters: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ActionsListResponse(BaseModel):
    actions: list[Action]
    total: int


class AuditListResponse(BaseModel):
    entries: list[AuditEntry]
    total: int


class ApproveResponse(BaseModel):
    action: Action
    correction: Correction | None = Field(
        default=None,
        description="Present when the approver edited the proposal before approving.",
    )


class CorrectionsListResponse(BaseModel):
    corrections: list[Correction]
    total: int


# ---------------------------------------------------------------------------
# Action endpoints
# ---------------------------------------------------------------------------


@router.post("/instinct/actions", response_model=Action, status_code=201)
async def propose_action(req: ProposeRequest):
    """Propose a new action for human approval."""
    return await _store().propose(
        pocket_id=req.pocket_id,
        title=req.title,
        description=req.description,
        recommendation=req.recommendation,
        trigger=req.trigger,
        category=req.category,
        priority=req.priority,
        parameters=req.parameters,
    )


@router.get("/instinct/actions/pending", response_model=list[Action])
async def pending_actions(pocket_id: str | None = Query(None)):
    """List actions waiting for human approval."""
    return await _store().pending(pocket_id=pocket_id)


@router.get("/instinct/actions", response_model=ActionsListResponse)
async def list_actions(
    pocket_id: str | None = Query(None, description="Filter by pocket ID"),
    status: str | None = Query(
        None, description="Filter by status: pending|approved|rejected|executed|failed"
    ),
    limit: int = Query(50, ge=1, le=500, description="Max actions to return"),
):
    """List all actions with optional status and pocket filters."""
    store = _store()
    status_enum = ActionStatus(status) if status else None
    actions = await store.list_actions(
        pocket_id=pocket_id,
        status=status_enum,
        limit=limit,
    )
    return ActionsListResponse(actions=actions, total=len(actions))


@router.post("/instinct/actions/{action_id}/approve", response_model=ApproveResponse)
async def approve_action(action_id: str, req: ApproveRequest | None = None):
    """Approve a pending action, optionally with edits.

    If the request body carries edits, the server diffs the stored proposal
    against the incoming shape and persists a Correction alongside the
    approval. Callers that want to approve unchanged can POST with no body.
    """
    store = _store()
    before = await store.get_action(action_id)
    if not before:
        raise HTTPException(404, "Action not found")

    req = req or ApproveRequest()
    after, edited_fields = _apply_edits(before, req)

    correction: Correction | None = None
    if edited_fields:
        patches = compute_patches(before, after)
        if patches:
            correction = Correction(
                action_id=before.id,
                pocket_id=before.pocket_id,
                actor=req.approver,
                patches=patches,
                context_summary=summarize_correction(before, patches),
                action_title=before.title,
            )
            await store.record_correction(correction)
            await _persist_edits(store, after, edited_fields)

    approved = await store.approve(action_id, approver=req.approver)
    if not approved:
        raise HTTPException(404, "Action not found")
    return ApproveResponse(action=approved, correction=correction)


@router.post("/instinct/actions/{action_id}/reject", response_model=Action)
async def reject_action(action_id: str, req: RejectRequest | None = None):
    """Reject a pending action with an optional reason."""
    reason = req.reason if req else ""
    action = await _store().reject(action_id, reason=reason)
    if not action:
        raise HTTPException(404, "Action not found")
    return action


def _apply_edits(before: Action, req: ApproveRequest) -> tuple[Action, set[str]]:
    """Return a copy of `before` with any non-null fields from `req` applied.

    Also returns the set of field names that were actually changed so the
    caller can decide whether to persist them back to the store.
    """
    edited: set[str] = set()
    update: dict[str, Any] = {}
    for field in ("title", "description", "recommendation", "category", "priority"):
        incoming = getattr(req, field)
        if incoming is not None and incoming != getattr(before, field):
            update[field] = incoming
            edited.add(field)
    if req.parameters is not None and req.parameters != before.parameters:
        update["parameters"] = req.parameters
        edited.add("parameters")
    return before.model_copy(update=update), edited


async def _persist_edits(store: Any, action: Action, edited: set[str]) -> None:
    """Persist the human edits back to the store before the approve update.

    Approval itself touches `status` and `approved_*` so we only write the
    content fields that actually changed — no redundant updates.
    """
    import aiosqlite

    assignments: list[str] = []
    params: list[Any] = []
    if "title" in edited:
        assignments.append("title = ?")
        params.append(action.title)
    if "description" in edited:
        assignments.append("description = ?")
        params.append(action.description)
    if "recommendation" in edited:
        assignments.append("recommendation = ?")
        params.append(action.recommendation)
    if "category" in edited:
        assignments.append("category = ?")
        params.append(action.category.value)
    if "priority" in edited:
        assignments.append("priority = ?")
        params.append(action.priority.value)
    if "parameters" in edited:
        import json as _json

        assignments.append("parameters = ?")
        params.append(_json.dumps(action.parameters))

    if not assignments:
        return

    assignments.append("updated_at = datetime('now')")
    params.append(action.id)
    async with aiosqlite.connect(store._db_path) as db:
        await db.execute(
            f"UPDATE instinct_actions SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Correction endpoints
# ---------------------------------------------------------------------------


@router.get("/instinct/corrections", response_model=CorrectionsListResponse)
async def list_corrections(
    pocket_id: str | None = Query(None, description="Filter by pocket ID"),
    action_id: str | None = Query(None, description="Filter by action ID"),
    limit: int = Query(100, ge=1, le=500),
):
    """List corrections captured when humans edited proposed actions."""
    store = _store()
    if action_id:
        corrections = await store.get_corrections_for_action(action_id)
    elif pocket_id:
        corrections = await store.get_corrections_for_pocket(pocket_id, limit=limit)
    else:
        raise HTTPException(400, "Provide pocket_id or action_id")
    return CorrectionsListResponse(corrections=corrections, total=len(corrections))


# ---------------------------------------------------------------------------
# Audit endpoints
# ---------------------------------------------------------------------------


@router.get("/instinct/audit", response_model=AuditListResponse)
async def query_audit(
    pocket_id: str | None = Query(None, description="Filter by pocket ID"),
    category: str | None = Query(
        None, description="Filter by category: decision|data|config|security"
    ),
    event: str | None = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=1, le=1000, description="Max entries to return"),
):
    """Query instinct audit log entries with optional filters."""
    entries = await _store().query_audit(
        pocket_id=pocket_id,
        category=category,
        event=event,
        limit=limit,
    )
    return AuditListResponse(entries=entries, total=len(entries))


@router.get("/instinct/audit/export")
async def export_audit(
    pocket_id: str | None = Query(None, description="Filter by pocket ID"),
):
    """Export the full instinct audit log as JSON for compliance."""
    data = await _store().export_audit(pocket_id=pocket_id)
    return Response(
        content=data,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="instinct_audit.json"'},
    )
