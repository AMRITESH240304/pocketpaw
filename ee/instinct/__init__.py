# Instinct — decision pipeline for Paw OS.
# Created: 2026-03-28 — Actions, approvals, audit log.
# Updated: 2026-03-30 — Exported ActionStatus, ActionCategory, ActionPriority, AuditCategory.
# Updated: 2026-04-12 (Move 1 PR-A) — Exported Correction, CorrectionPatch, compute_patches.
# The decision loop: Agent proposes -> Human approves (optionally edits) ->
# Action executes -> Correction captured -> Soul learns.

from ee.instinct.correction import (
    Correction,
    CorrectionPatch,
    compute_patches,
    summarize_correction,
)
from ee.instinct.models import (
    Action,
    ActionCategory,
    ActionContext,
    ActionPriority,
    ActionStatus,
    ActionTrigger,
    AuditCategory,
    AuditEntry,
)
from ee.instinct.store import InstinctStore

__all__ = [
    "Action",
    "ActionCategory",
    "ActionContext",
    "ActionPriority",
    "ActionStatus",
    "ActionTrigger",
    "AuditCategory",
    "AuditEntry",
    "Correction",
    "CorrectionPatch",
    "InstinctStore",
    "compute_patches",
    "summarize_correction",
]
